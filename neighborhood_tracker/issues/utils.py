"""
Utility helpers: nearby / duplicate issue detection using Haversine distance.
No external geo libraries needed - works fine for a single-neighborhood scale app.
"""
from .models import Issue

DUPLICATE_RADIUS_METERS = 60      # if same category within this range -> likely duplicate
NEARBY_RADIUS_METERS = 2000       # "issues near you" default radius

# Radius presets shown as toggle buttons on the Nearby Issues page.
NEARBY_RADIUS_PRESETS = [
    (1000, '1 km'),
    (2000, '2 km'),
    (5000, '5 km'),
]


def find_nearby_issues(lat, lng, radius=NEARBY_RADIUS_METERS, exclude_pk=None, category_id=None):
    """Returns list of (issue, distance_m) sorted by distance, within radius meters."""
    qs = Issue.objects.select_related('category', 'reported_by').exclude(status='resolved')
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if category_id:
        qs = qs.filter(category_id=category_id)

    results = []
    for issue in qs:
        d = issue.distance_to(lat, lng)
        if d <= radius:
            results.append((issue, round(d)))
    results.sort(key=lambda pair: pair[1])
    return results


ESCALATION_DAYS = 7  # open issues older than this get auto-escalated


def find_possible_duplicates(lat, lng, category_id):
    """Same-category issues very close by - flagged as possible duplicates."""
    return find_nearby_issues(lat, lng, radius=DUPLICATE_RADIUS_METERS, category_id=category_id)


def check_and_escalate_overdue_issues():
    """Marks open, unescalated issues older than ESCALATION_DAYS as escalated,
    and notifies staff. Called lazily from a few frequently-visited views
    (home, officer_dashboard) instead of needing a cron job / Celery worker -
    simple and reliable for a small-to-medium deployment without extra infra."""
    from django.utils import timezone
    from datetime import timedelta
    from .models import Issue, Notification, User, AuditLog

    cutoff = timezone.now() - timedelta(days=ESCALATION_DAYS)
    overdue = (Issue.objects
               .filter(escalated=False, created_at__lte=cutoff)
               .exclude(status='resolved'))

    escalated_count = 0
    for issue in overdue:
        issue.escalated = True
        issue.escalated_at = timezone.now()
        issue.save(update_fields=['escalated', 'escalated_at'])

        # Notify staff in the issue's department (or all staff if no department set).
        if issue.department_id:
            staff_qs = User.objects.filter(is_staff=True, profile__department_id=issue.department_id)
        else:
            staff_qs = User.objects.filter(is_staff=True)

        Notification.objects.bulk_create([
            Notification(
                user=staff, issue=issue,
                message=f"⚠️ ESCALATED: \"{issue.title}\" has been open for over {ESCALATION_DAYS} days without resolution"
            ) for staff in staff_qs
        ])
        AuditLog.log(actor=None, action='other', issue=issue, detail=f"Auto-escalated after {ESCALATION_DAYS}+ days open")
        escalated_count += 1

    return escalated_count


def estimated_resolution_days(category):
    """Average days-to-resolve for a category, computed from real historical data
    (IssueStatusHistory 'resolved' entries minus the issue's created_at). Returns
    None if there isn't enough history yet to estimate confidently."""
    from .models import IssueStatusHistory
    if category is None:
        return None

    histories = (IssueStatusHistory.objects
                 .filter(status='resolved', issue__category=category)
                 .select_related('issue'))
    total_days = 0.0
    count = 0
    for h in histories:
        if h.issue.created_at:
            delta = h.created_at - h.issue.created_at
            total_days += delta.total_seconds() / 86400
            count += 1

    if count < 2:  # not enough history to give a confident estimate
        return None
    return round(total_days / count, 1)
