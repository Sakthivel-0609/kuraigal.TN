from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth import views as auth_views
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.utils.translation import gettext as _
from django.core.paginator import Paginator
from django.core.cache import cache
from django.template.loader import get_template
from datetime import timedelta

from .models import Issue, Category, Comment, Notification, IssueStatusHistory, UserProfile, Department, OfficerRating, Volunteer, Feedback, AuditLog
from .forms import IssueForm, CommentForm, SignUpForm
from .utils import (
    find_nearby_issues, find_possible_duplicates, NEARBY_RADIUS_METERS, NEARBY_RADIUS_PRESETS,
    check_and_escalate_overdue_issues, estimated_resolution_days, ESCALATION_DAYS,
)
from .ai import suggest_category, suggest_priority, is_spam_text, generate_summary, chatbot_reply


# ------------------------------------------------------------------- homepage
def home(request):
    """
    Government Smart City Portal landing page.
    Every number shown here is computed live from the database - no fake data.
    """
    # SLA check: escalate any open issues that have been sitting too long.
    # Throttled via cache so it runs at most once every 5 minutes, not on every
    # single page view.
    if cache.get('escalation_check_lock') is None:
        cache.set('escalation_check_lock', True, 300)
        check_and_escalate_overdue_issues()

    all_issues = Issue.objects.all()
    week_ago = timezone.now() - timedelta(days=7)

    stats = {
        'total_issues': all_issues.count(),
        'open_issues': all_issues.filter(status='open').count(),
        'in_progress_issues': all_issues.filter(status='in_progress').count(),
        'resolved_issues': all_issues.filter(status='resolved').count(),
        'emergency_active': all_issues.filter(is_emergency=True).exclude(status='resolved').count(),
        'citizens': User.objects.count(),
        'categories_count': Category.objects.count(),
        'this_week': all_issues.filter(created_at__gte=week_ago).count(),
    }
    total = stats['total_issues']
    stats['resolution_rate'] = round((stats['resolved_issues'] / total) * 100, 1) if total else 0

    recent_issues = (Issue.objects.select_related('category', 'reported_by')
                      .annotate(votes=Count('upvotes'))
                      .order_by('-is_emergency', '-created_at')[:6])

    emergency_issues = (Issue.objects.filter(is_emergency=True).exclude(status='resolved')
                         .select_related('category')[:4])

    top_contributors = UserProfile.objects.select_related('user').order_by('-points')[:5]

    categories = Category.objects.annotate(issue_count=Count('issues'))[:10]

    context = {
        'stats': stats,
        'recent_issues': recent_issues,
        'emergency_issues': emergency_issues,
        'top_contributors': top_contributors,
        'categories': categories,
    }
    return render(request, 'issues/home.html', context)


# ---------------------------------------------------------------- issue list
def issue_list(request):
    issues = Issue.objects.select_related('category', 'reported_by').annotate(votes=Count('upvotes'))

    category_id = request.GET.get('category')
    status = request.GET.get('status')
    search = request.GET.get('q')
    emergency_only = request.GET.get('emergency')
    area = request.GET.get('area')
    department_id = request.GET.get('department')
    ward = request.GET.get('ward')

    if category_id:
        issues = issues.filter(category_id=category_id)
    if status:
        issues = issues.filter(status=status)
    if search:
        # AI Smart Search: plain text match, PLUS category match inferred from
        # natural-language keywords (e.g. "street dark at night" also finds
        # Streetlight issues even without that exact word in the title).
        search_q = Q(title__icontains=search) | Q(description__icontains=search) | Q(address__icontains=search)
        implied_category = suggest_category(search, Category.objects.all())
        if implied_category:
            search_q |= Q(category=implied_category)
        issues = issues.filter(search_q).distinct()
    if emergency_only:
        issues = issues.filter(is_emergency=True)
    if area:
        issues = issues.filter(address=area)
    if department_id:
        issues = issues.filter(department_id=department_id)
    if ward:
        issues = issues.filter(ward=ward)

    sort = request.GET.get('sort', 'recent')
    if sort == 'votes':
        issues = issues.order_by('-is_emergency', '-votes', '-created_at')
    else:
        issues = issues.order_by('-is_emergency', '-created_at')

    categories = Category.objects.all()
    areas = (Issue.objects.exclude(address='').values_list('address', flat=True)
             .distinct().order_by('address')[:50])
    departments = Department.objects.all()
    wards = (Issue.objects.exclude(ward='').values_list('ward', flat=True)
             .distinct().order_by('ward')[:50])

    # Performance: paginate instead of loading every matching issue on one page.
    paginator = Paginator(issues, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Preserve all current filters when building pagination links.
    querydict = request.GET.copy()
    querydict.pop('page', None)
    base_query = querydict.urlencode()

    context = {
        'issues': page_obj,
        'page_obj': page_obj,
        'base_query': base_query,
        'categories': categories,
        'areas': areas,
        'departments': departments,
        'wards': wards,
        'selected_category': category_id,
        'selected_status': status,
        'selected_area': area or '',
        'selected_department': department_id or '',
        'selected_ward': ward or '',
        'search': search or '',
        'sort': sort,
        'emergency_only': emergency_only,
        'status_choices': Issue.STATUS_CHOICES,
    }
    return render(request, 'issues/issue_list.html', context)


# ------------------------------------------------------------ issue map data
def issue_map_data(request):
    """JSON markers for the Issue List 'Map View' toggle - respects the same filters."""
    issues = Issue.objects.select_related('category').only(
        'id', 'title', 'latitude', 'longitude', 'status', 'is_emergency', 'category'
    )

    category_id = request.GET.get('category')
    status = request.GET.get('status')
    search = request.GET.get('q')
    emergency_only = request.GET.get('emergency')
    area = request.GET.get('area')

    if category_id:
        issues = issues.filter(category_id=category_id)
    if status:
        issues = issues.filter(status=status)
    if search:
        issues = issues.filter(Q(title__icontains=search) | Q(description__icontains=search))
    if emergency_only:
        issues = issues.filter(is_emergency=True)
    if area:
        issues = issues.filter(address=area)

    data = [{
        'id': i.pk,
        'title': i.title,
        'lat': i.latitude,
        'lng': i.longitude,
        'status': i.status,
        'status_label': i.get_status_display(),
        'is_emergency': i.is_emergency,
        'category_icon': i.category.icon if i.category else '',
        'url': i.get_absolute_url(),
    } for i in issues]
    return JsonResponse(data, safe=False)


# -------------------------------------------------------------- issue detail
def issue_detail(request, pk):
    issue = get_object_or_404(Issue.objects.select_related('category', 'reported_by'), pk=pk)
    comments = issue.comments.select_related('user').prefetch_related('likes').annotate(likes_count=Count('likes'))

    comment_sort = request.GET.get('comment_sort', 'newest')
    if comment_sort == 'oldest':
        comments = comments.order_by('created_at')
    elif comment_sort == 'liked':
        comments = comments.order_by('-likes_count', '-created_at')
    else:
        comments = comments.order_by('-created_at')

    history = issue.history.select_related('changed_by')

    if request.method == 'POST' and request.user.is_authenticated:
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment_text = comment_form.cleaned_data['text']

            # AI Spam Detection: reject obvious spam/gibberish before it ever saves.
            if is_spam_text(comment_text):
                messages.error(request, _("This comment looks like spam or is too short and was not posted. Please write a genuine comment."))
                return redirect('issue_detail', pk=issue.pk)

            comment = comment_form.save(commit=False)
            comment.issue = issue
            comment.user = request.user
            comment.save()

            profile, _created = UserProfile.objects.get_or_create(user=request.user)
            profile.add_points(1)

            if issue.reported_by != request.user:
                Notification.objects.create(
                    user=issue.reported_by,
                    issue=issue,
                    message=f"{request.user.username} commented on your issue \"{issue.title}\""
                )
            return redirect('issue_detail', pk=issue.pk)
    else:
        comment_form = CommentForm()

    has_upvoted = request.user.is_authenticated and issue.upvotes.filter(pk=request.user.pk).exists()
    has_bookmarked = request.user.is_authenticated and issue.bookmarks.filter(pk=request.user.pk).exists()
    nearby = find_nearby_issues(issue.latitude, issue.longitude, exclude_pk=issue.pk)[:6]

    existing_rating = OfficerRating.objects.filter(issue=issue).first()
    can_rate_officer = (
        request.user.is_authenticated
        and issue.status == 'resolved'
        and issue.assigned_officer_id
        and issue.reported_by_id == request.user.id
        and existing_rating is None
    )

    est_resolution_days = None
    if issue.status != 'resolved':
        est_resolution_days = estimated_resolution_days(issue.category)

    context = {
        'issue': issue,
        'comments': comments,
        'comment_form': comment_form,
        'comment_sort': comment_sort,
        'has_upvoted': has_upvoted,
        'has_bookmarked': has_bookmarked,
        'history': history,
        'nearby': nearby,
        'existing_rating': existing_rating,
        'can_rate_officer': can_rate_officer,
        'est_resolution_days': est_resolution_days,
    }
    if request.user.is_superuser:
        context['all_departments'] = Department.objects.all()
        context['staff_users'] = User.objects.filter(is_staff=True).order_by('username')
    return render(request, 'issues/issue_detail.html', context)


# ------------------------------------------------------------------ comments
@login_required
def toggle_comment_like(request, pk):
    """AJAX endpoint: like/unlike a comment. Returns the new like count as JSON."""
    comment = get_object_or_404(Comment, pk=pk)
    if comment.likes.filter(pk=request.user.pk).exists():
        comment.likes.remove(request.user)
        liked = False
    else:
        comment.likes.add(request.user)
        liked = True
    return JsonResponse({'likes': comment.like_count(), 'liked': liked})


@login_required
def edit_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk, user=request.user)
    if request.method == 'POST':
        form = CommentForm(request.POST, instance=comment)
        if form.is_valid() and not is_spam_text(form.cleaned_data['text']):
            comment = form.save(commit=False)
            comment.is_edited = True
            comment.save()
    return redirect('issue_detail', pk=comment.issue.pk)


@login_required
def delete_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk, user=request.user)
    issue_pk = comment.issue.pk
    if request.method == 'POST':
        comment.delete()
    return redirect('issue_detail', pk=issue_pk)


# ------------------------------------------------------------ officer rating
@login_required
def rate_officer(request, pk):
    """Citizen rates the officer who resolved their complaint. One rating per issue."""
    issue = get_object_or_404(Issue, pk=pk)

    eligible = (
        issue.status == 'resolved'
        and issue.assigned_officer_id
        and issue.reported_by_id == request.user.id
        and not OfficerRating.objects.filter(issue=issue).exists()
    )

    if eligible and request.method == 'POST':
        try:
            stars = int(request.POST.get('stars', 0))
        except ValueError:
            stars = 0
        if 1 <= stars <= 5:
            OfficerRating.objects.create(
                issue=issue,
                officer=issue.assigned_officer,
                rated_by=request.user,
                stars=stars,
                comment=request.POST.get('comment', '').strip()[:255],
            )
            Notification.objects.create(
                user=issue.assigned_officer,
                issue=issue,
                message=f"{request.user.username} rated your work on \"{issue.title}\": {stars}★"
            )
            messages.success(request, _("Thanks for rating the officer's work!"))
    return redirect('issue_detail', pk=issue.pk)


# ------------------------------------------------------------- report issue
@login_required
def report_issue(request):
    if request.method == 'POST':
        form = IssueForm(request.POST, request.FILES)
        if form.is_valid():
            issue = form.save(commit=False)
            issue.reported_by = request.user

            # AI Priority Detection: classify severity from the free-text description.
            ai_priority = suggest_priority(f"{issue.title} {issue.description}")
            issue.priority = ai_priority
            if ai_priority == 'emergency':
                issue.is_emergency = True  # never auto-downgrades a citizen's manual flag

            issue.save()

            # Emergency broadcast: immediately notify all staff/officers.
            if issue.is_emergency:
                emergency_label = dict(Issue.EMERGENCY_TYPE_CHOICES).get(issue.emergency_type, _('Emergency'))
                staff_users = User.objects.filter(is_staff=True).exclude(pk=request.user.pk)
                Notification.objects.bulk_create([
                    Notification(
                        user=staff, issue=issue,
                        message=f"🚨 {emergency_label} reported: \"{issue.title}\" at {issue.address or 'unknown location'}"
                    ) for staff in staff_users
                ])

            # Email confirmation with PDF attachment, if the citizen provided an email.
            if issue.reporter_email:
                email_sent = send_report_confirmation_email(request, issue)
                if email_sent:
                    messages.success(request, _("Issue reported successfully. A confirmation email with your complaint PDF has been sent."))
                else:
                    messages.success(request, _("Issue reported successfully. (We couldn't send the confirmation email - please check the email address.)"))
            else:
                messages.success(request, _("Issue reported successfully. Thanks for helping the neighborhood!"))
            return redirect('issue_detail', pk=issue.pk)
        else:
            if 'latitude' in form.errors or 'longitude' in form.errors:
                messages.error(request, _("Please select a location on the map before submitting."))
            else:
                messages.error(request, _("Please fix the errors below and try again."))
    else:
        form = IssueForm()
    return render(request, 'issues/report_issue.html', {'form': form})


def ai_suggest_view(request):
    """AJAX endpoint: AI Category + Priority suggestion, called as the citizen types
    the title/description on the Report Issue page."""
    title = request.GET.get('title', '')
    description = request.GET.get('description', '')
    text = f"{title} {description}".strip()

    category = suggest_category(text, Category.objects.all())
    priority = suggest_priority(text)

    return JsonResponse({
        'category_id': category.id if category else None,
        'category_name': category.name if category else None,
        'category_icon': category.icon if category else '',
        'priority': priority,
        'priority_label': dict(Issue.PRIORITY_CHOICES).get(priority, priority),
    })


def check_duplicate(request):
    """AJAX endpoint: called from the report form after user picks a location + category."""
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
    except (TypeError, ValueError):
        return JsonResponse({'duplicates': []})

    category_id = request.GET.get('category') or None
    duplicates = find_possible_duplicates(lat, lng, category_id)

    data = [{
        'id': issue.pk,
        'title': issue.title,
        'status': issue.get_status_display(),
        'distance': dist,
        'url': issue.get_absolute_url(),
        'votes': issue.upvote_count(),
    } for issue, dist in duplicates[:5]]

    return JsonResponse({'duplicates': data})


# ------------------------------------------------------------------ upvote
@login_required
def toggle_upvote(request, pk):
    issue = get_object_or_404(Issue, pk=pk)
    if issue.upvotes.filter(pk=request.user.pk).exists():
        issue.upvotes.remove(request.user)
    else:
        issue.upvotes.add(request.user)
        if issue.reported_by != request.user:
            profile, _created = UserProfile.objects.get_or_create(user=issue.reported_by)
            profile.add_points(2)
            Notification.objects.create(
                user=issue.reported_by,
                issue=issue,
                message=f"{request.user.username} upvoted your issue \"{issue.title}\""
            )
    return redirect(request.META.get('HTTP_REFERER', 'issue_list'))


# ---------------------------------------------------------------- bookmarks
@login_required
def toggle_bookmark(request, pk):
    issue = get_object_or_404(Issue, pk=pk)
    if issue.bookmarks.filter(pk=request.user.pk).exists():
        issue.bookmarks.remove(request.user)
    else:
        issue.bookmarks.add(request.user)
    return redirect(request.META.get('HTTP_REFERER', 'issue_list'))


@login_required
def my_bookmarks_view(request):
    bookmarked = (Issue.objects.filter(bookmarks=request.user)
                  .select_related('category', 'reported_by')
                  .annotate(votes=Count('upvotes'))
                  .order_by('-is_emergency', '-created_at'))
    return render(request, 'issues/bookmarks.html', {'bookmarked': bookmarked})


# -------------------------------------------------------------- status update
@login_required
def update_status(request, pk):
    """Status update - restrict to staff in production."""
    issue = get_object_or_404(Issue, pk=pk)
    if request.user.is_staff and request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(Issue.STATUS_CHOICES) and new_status != issue.status:
            issue.status = new_status
            issue.save()
            IssueStatusHistory.objects.create(
                issue=issue, status=new_status, changed_by=request.user,
                note=f"Status changed to {issue.get_status_display()}"
            )
            Notification.objects.create(
                user=issue.reported_by,
                issue=issue,
                message=f"Your issue \"{issue.title}\" is now {issue.get_status_display()}"
            )
            if new_status == 'resolved':
                profile, _created = UserProfile.objects.get_or_create(user=issue.reported_by)
                profile.add_points(20)
            AuditLog.log(request.user, 'status_change', issue=issue,
                         detail=f"Status -> {issue.get_status_display()}", request=request)
            messages.success(request, _("Status updated."))
    return redirect('issue_detail', pk=issue.pk)


# ------------------------------------------------------- officer assignment
@login_required
def assign_officer(request, pk):
    """Admin-only: assign (or reassign) an officer to an issue."""
    issue = get_object_or_404(Issue, pk=pk)
    if not request.user.is_superuser:
        messages.error(request, _("Only administrators can assign officers."))
        return redirect('issue_detail', pk=issue.pk)
    if request.method == 'POST':
        officer_id = request.POST.get('officer')
        if officer_id:
            officer = get_object_or_404(User, pk=officer_id, is_staff=True)
            issue.assigned_officer = officer
            issue.save(update_fields=['assigned_officer'])
            Notification.objects.create(
                user=officer,
                issue=issue,
                message=f"You have been assigned to \"{issue.title}\""
            )
            AuditLog.log(request.user, 'officer_assigned', issue=issue, detail=f"Assigned to {officer.username}", request=request)
            messages.success(request, _("Officer assigned."))
        else:
            issue.assigned_officer = None
            issue.save(update_fields=['assigned_officer'])
            AuditLog.log(request.user, 'officer_assigned', issue=issue, detail="Unassigned", request=request)
            messages.success(request, _("Officer unassigned."))
    return redirect('issue_detail', pk=issue.pk)


@login_required
def assign_department(request, pk):
    """Admin-only: reassign an issue to a different department."""
    issue = get_object_or_404(Issue, pk=pk)
    if not request.user.is_superuser:
        messages.error(request, _("Only administrators can reassign departments."))
        return redirect('issue_detail', pk=issue.pk)
    if request.method == 'POST':
        department_id = request.POST.get('department')
        issue.department_id = department_id or None
        issue.save(update_fields=['department'])
        AuditLog.log(request.user, 'department_reassigned', issue=issue,
                     detail=str(issue.department) if issue.department_id else "Cleared", request=request)
        messages.success(request, _("Department updated."))
    return redirect('issue_detail', pk=issue.pk)


# ---------------------------------------------------------------- officer
@login_required
def officer_dashboard(request):
    """Officers see complaints assigned to them; staff without an officer flag
    see everything in their department (or all issues, if no department set)."""
    profile, _created = UserProfile.objects.get_or_create(user=request.user)
    if not (profile.is_officer or request.user.is_staff):
        messages.error(request, _("You don't have access to the Officer Dashboard."))
        return redirect('home')

    assigned = (Issue.objects.filter(assigned_officer=request.user)
                .select_related('category', 'department', 'reported_by')
                .order_by('-is_emergency', '-created_at'))

    dept_queue = Issue.objects.none()
    if profile.department:
        dept_queue = (Issue.objects.filter(department=profile.department, assigned_officer__isnull=True)
                      .exclude(status='resolved')
                      .select_related('category', 'reported_by')
                      .order_by('-is_emergency', '-created_at'))

    stats = {
        'assigned_total': assigned.count(),
        'assigned_open': assigned.filter(status='open').count(),
        'assigned_in_progress': assigned.filter(status='in_progress').count(),
        'assigned_resolved': assigned.filter(status='resolved').count(),
        'avg_rating': OfficerRating.objects.filter(officer=request.user).aggregate(avg=Avg('stars'))['avg'],
        'rating_count': OfficerRating.objects.filter(officer=request.user).count(),
        'queue_count': dept_queue.count(),
    }

    context = {
        'profile': profile,
        'assigned': assigned,
        'dept_queue': dept_queue,
        'stats': stats,
    }
    return render(request, 'issues/officer_dashboard.html', context)


@login_required
def officer_update(request, pk):
    """Officer-only: update status + add a remark, from the Officer Dashboard."""
    issue = get_object_or_404(Issue, pk=pk)
    profile, _created = UserProfile.objects.get_or_create(user=request.user)

    can_act = request.user.is_staff or profile.is_officer
    if can_act and request.method == 'POST':
        new_status = request.POST.get('status')
        remark = request.POST.get('remark', '').strip()
        completion_photo = request.FILES.get('completion_image')

        if completion_photo:
            issue.completion_image = completion_photo
            issue.save(update_fields=['completion_image'])

        if new_status in dict(Issue.STATUS_CHOICES) and new_status != issue.status:
            issue.status = new_status
            issue.save()
            IssueStatusHistory.objects.create(
                issue=issue, status=new_status, changed_by=request.user,
                note=remark or f"Status changed to {issue.get_status_display()} by officer"
            )
            Notification.objects.create(
                user=issue.reported_by,
                issue=issue,
                message=f"Your issue \"{issue.title}\" is now {issue.get_status_display()}"
            )
            if new_status == 'resolved':
                reporter_profile, _c = UserProfile.objects.get_or_create(user=issue.reported_by)
                reporter_profile.add_points(20)
        elif remark:
            IssueStatusHistory.objects.create(issue=issue, status=issue.status, changed_by=request.user, note=remark)

        messages.success(request, _("Update saved."))
    return redirect('officer_dashboard')


# ------------------------------------------------------------- activity log
@login_required
def activity_log_view(request):
    """Staff-only: read-only feed of recent staff actions for accountability."""
    if not request.user.is_staff:
        messages.error(request, _("You don't have access to the Activity Log."))
        return redirect('home')

    logs = AuditLog.objects.select_related('actor', 'issue').all()[:200]
    return render(request, 'issues/activity_log.html', {'logs': logs})


# ---------------------------------------------------------------- heatmap
def heatmap_view(request):
    categories = Category.objects.all()
    return render(request, 'issues/heatmap.html', {'categories': categories})


def heatmap_data(request):
    """Returns [[lat, lng, intensity], ...] for Leaflet.heat. Emergency issues weigh more."""
    issues = Issue.objects.exclude(status='resolved')

    category_id = request.GET.get('category')
    if category_id:
        issues = issues.filter(category_id=category_id)

    data = []
    for i in issues.only('latitude', 'longitude', 'is_emergency'):
        intensity = 1.0 if i.is_emergency else 0.5
        data.append([i.latitude, i.longitude, intensity])
    return JsonResponse(data, safe=False)


# ---------------------------------------------------------------- emergency
def emergency_dashboard(request):
    """Live dashboard of all active (unresolved) emergency complaints, grouped by type."""
    active_emergencies = (Issue.objects.filter(is_emergency=True)
                           .exclude(status='resolved')
                           .select_related('category', 'department', 'reported_by')
                           .order_by('-created_at'))

    resolved_today = Issue.objects.filter(
        is_emergency=True, status='resolved', updated_at__date=timezone.now().date()
    ).count()

    by_type = (active_emergencies.values('emergency_type')
               .annotate(count=Count('id')).order_by('-count'))
    type_labels = dict(Issue.EMERGENCY_TYPE_CHOICES)
    by_type_display = [
        {'type': row['emergency_type'], 'label': type_labels.get(row['emergency_type'], row['emergency_type'] or 'Unspecified'), 'count': row['count']}
        for row in by_type
    ]

    context = {
        'active_emergencies': active_emergencies,
        'active_count': active_emergencies.count(),
        'resolved_today': resolved_today,
        'by_type': by_type_display,
        'emergency_type_choices': Issue.EMERGENCY_TYPE_CHOICES,
    }
    return render(request, 'issues/emergency_dashboard.html', context)


# --------------------------------------------------------------- departments
def department_list_view(request):
    """Public directory of government departments with live performance stats."""
    departments = Department.objects.all()
    return render(request, 'issues/departments.html', {'departments': departments})


# ------------------------------------------------------------- nearby issues
def nearby_issues_view(request):
    """User-location based nearby complaints page. Supports a radius toggle
    (1km/2km/5km) and sorting by distance, priority (emergency-first), or newest."""
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')

    valid_radii = [r for r, _ in NEARBY_RADIUS_PRESETS]
    try:
        radius = int(request.GET.get('radius', NEARBY_RADIUS_METERS))
        if radius not in valid_radii:
            radius = NEARBY_RADIUS_METERS
    except (TypeError, ValueError):
        radius = NEARBY_RADIUS_METERS

    sort = request.GET.get('sort', 'distance')

    nearby = []
    if lat and lng:
        try:
            nearby = find_nearby_issues(float(lat), float(lng), radius=radius)
            if sort == 'priority':
                nearby.sort(key=lambda pair: (not pair[0].is_emergency, pair[1]))
            elif sort == 'newest':
                nearby.sort(key=lambda pair: pair[0].created_at, reverse=True)
            elif sort == 'votes':
                nearby.sort(key=lambda pair: pair[0].upvote_count(), reverse=True)
            # 'distance' is already the default order from find_nearby_issues
        except ValueError:
            nearby = []

    context = {
        'nearby': nearby,
        'has_location': bool(lat and lng),
        'radius': radius,
        'radius_presets': NEARBY_RADIUS_PRESETS,
        'sort': sort,
    }
    return render(request, 'issues/nearby.html', context)


# --------------------------------------------------------------- analytics
@login_required
def export_issues_csv(request):
    """Exports issues as CSV (opens natively in Excel) - respects the same
    filters as the Issue List page, so 'export what I'm currently viewing' works.
    Staff/officers only - citizens don't get bulk data export."""
    if not request.user.is_staff:
        messages.error(request, _("You don't have permission to export this data."))
        return redirect('issue_list')

    import csv

    issues = Issue.objects.select_related('category', 'department', 'reported_by').annotate(votes=Count('upvotes'))

    category_id = request.GET.get('category')
    status = request.GET.get('status')
    department_id = request.GET.get('department')
    ward = request.GET.get('ward')
    emergency_only = request.GET.get('emergency')

    if category_id:
        issues = issues.filter(category_id=category_id)
    if status:
        issues = issues.filter(status=status)
    if department_id:
        issues = issues.filter(department_id=department_id)
    if ward:
        issues = issues.filter(ward=ward)
    if emergency_only:
        issues = issues.filter(is_emergency=True)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="kuraigal_tn_issues_export.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Tracking Number', 'Title', 'Category', 'Department', 'Ward', 'Status', 'Priority',
        'Emergency', 'Address', 'Latitude', 'Longitude', 'Reported By', 'Upvotes',
        'Escalated', 'Reported At',
    ])
    for issue in issues.order_by('-created_at'):
        writer.writerow([
            issue.tracking_number,
            issue.title,
            issue.category.name if issue.category else '',
            issue.department.name if issue.department else '',
            issue.ward,
            issue.get_status_display(),
            issue.get_priority_display(),
            'Yes' if issue.is_emergency else 'No',
            issue.address,
            issue.latitude,
            issue.longitude,
            issue.display_reporter_name,
            issue.votes,
            'Yes' if issue.escalated else 'No',
            issue.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
    return response


def analytics_dashboard(request):
    # Performance: these aggregate queries scan the whole Issue table, so cache
    # the computed context for a short window instead of recomputing on every hit.
    context = cache.get('analytics_dashboard_context')
    if context is None:
        by_category = (Issue.objects.values('category__name', 'category__icon')
                       .annotate(count=Count('id')).order_by('-count'))
        by_status = Issue.objects.values('status').annotate(count=Count('id')).order_by('status')
        by_area = (Issue.objects.exclude(address='').values('address')
                   .annotate(count=Count('id')).order_by('-count')[:10])
        by_ward = (Issue.objects.exclude(ward='').values('ward')
                   .annotate(
                       count=Count('id'),
                       resolved_count=Count('id', filter=Q(status='resolved')),
                   ).order_by('-count')[:15])

        total_issues = Issue.objects.count()
        resolved = Issue.objects.filter(status='resolved').count()
        emergency = Issue.objects.filter(is_emergency=True).exclude(status='resolved').count()
        resolution_rate = round((resolved / total_issues) * 100, 1) if total_issues else 0

        department_performance = [
            {'name': d.name, 'total': d.total_issue_count(), 'resolved': d.resolved_issue_count(), 'rate': d.resolution_rate()}
            for d in Department.objects.all() if d.total_issue_count() > 0
        ]
        department_performance.sort(key=lambda d: d['rate'], reverse=True)

        context = {
            'by_category': list(by_category),
            'by_status': list(by_status),
            'by_area': list(by_area),
            'by_ward': list(by_ward),
            'department_performance': department_performance,
            'total_issues': total_issues,
            'resolved': resolved,
            'emergency': emergency,
            'resolution_rate': resolution_rate,
        }
        cache.set('analytics_dashboard_context', context, 120)  # 2 minutes
    return render(request, 'issues/analytics.html', context)


def analytics_pdf(request):
    """Export a simple analytics summary as PDF (requires reportlab)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
    except ImportError:
        return HttpResponse(
            "PDF export requires the 'reportlab' package. Install it with: pip install reportlab",
            status=500, content_type='text/plain'
        )

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="neighborhood_report.pdf"'

    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    y = height - 2 * cm

    p.setFont("Helvetica-Bold", 18)
    p.drawString(2 * cm, y, "Neighborhood Issue Report")
    y -= 1 * cm

    p.setFont("Helvetica", 10)
    total = Issue.objects.count()
    resolved = Issue.objects.filter(status='resolved').count()
    p.drawString(2 * cm, y, f"Total issues: {total}    Resolved: {resolved}")
    y -= 1 * cm

    p.setFont("Helvetica-Bold", 12)
    p.drawString(2 * cm, y, "By Category")
    y -= 0.7 * cm
    p.setFont("Helvetica", 10)
    for row in Issue.objects.values('category__name').annotate(count=Count('id')).order_by('-count'):
        p.drawString(2.3 * cm, y, f"- {row['category__name'] or 'Uncategorized'}: {row['count']}")
        y -= 0.5 * cm
        if y < 3 * cm:
            p.showPage()
            y = height - 2 * cm

    y -= 0.5 * cm
    p.setFont("Helvetica-Bold", 12)
    p.drawString(2 * cm, y, "Recent Issues")
    y -= 0.7 * cm
    p.setFont("Helvetica", 9)
    for issue in Issue.objects.order_by('-created_at')[:25]:
        line = f"[{issue.get_status_display()}] {issue.title} ({issue.address or 'no address'})"
        p.drawString(2.3 * cm, y, line[:100])
        y -= 0.45 * cm
        if y < 2 * cm:
            p.showPage()
            y = height - 2 * cm

    p.showPage()
    p.save()
    return response


def _build_issue_pdf_bytes(request, issue):
    """Builds an official-style Government of Tamil Nadu Citizen Grievance
    Acknowledgement Receipt for a single complaint, and returns raw PDF bytes.
    Shared by the download view (issue_pdf) and the email-confirmation sender."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    )
    from reportlab.lib.utils import ImageReader
    import io
    import os
    from django.conf import settings

    NAVY = colors.HexColor('#0B2545')
    GOLD = colors.HexColor('#B8860B')
    LIGHT_BG = colors.HexColor('#F4F6F9')
    GRAY = colors.HexColor('#5C6B7A')

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='GovHeaderTitle', fontName='Helvetica-Bold', fontSize=13,
                               textColor=NAVY, alignment=TA_CENTER, leading=16))
    styles.add(ParagraphStyle(name='GovHeaderSub', fontName='Helvetica', fontSize=9.5,
                               textColor=GRAY, alignment=TA_CENTER, leading=12))
    styles.add(ParagraphStyle(name='DocTitle', fontName='Helvetica-Bold', fontSize=12,
                               textColor=colors.white, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='FieldLabel', fontName='Helvetica-Bold', fontSize=8.5,
                               textColor=GRAY, leading=11))
    styles.add(ParagraphStyle(name='FieldValue', fontName='Helvetica', fontSize=9.5,
                               textColor=colors.HexColor('#1a1a1a'), leading=12.5))
    styles.add(ParagraphStyle(name='SectionHeading', fontName='Helvetica-Bold', fontSize=10.5,
                               textColor=NAVY, leading=13, spaceBefore=8, spaceAfter=4))
    styles.add(ParagraphStyle(name='BodyText9', fontName='Helvetica', fontSize=9.5,
                               textColor=colors.HexColor('#1a1a1a'), leading=13.5))
    styles.add(ParagraphStyle(name='Disclaimer', fontName='Helvetica-Oblique', fontSize=7.5,
                               textColor=GRAY, alignment=TA_CENTER, leading=10))

    story = []

    # ---------------------------------------------------------------- header
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'icon-192.png')
    logo_flowable = RLImage(logo_path, width=1.7 * cm, height=1.7 * cm) if os.path.exists(logo_path) else Spacer(1.7 * cm, 1.7 * cm)

    header_text = [
        Paragraph("GOVERNMENT OF TAMIL NADU", styles['GovHeaderTitle']),
        Paragraph("Kuraigal.TN — Citizen Grievance Management Portal", styles['GovHeaderSub']),
        Paragraph(issue.department.name if issue.department else "Municipal Administration", styles['GovHeaderSub']),
    ]
    header_table = Table([[logo_flowable, header_text]], colWidths=[2.2 * cm, 14.8 * cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.15 * cm))
    story.append(Table([['']], colWidths=[17 * cm], rowHeights=[0.06 * cm],
                        style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), NAVY)])))
    story.append(Spacer(1, 0.35 * cm))

    # ------------------------------------------------------------ doc title
    story.append(Table([[Paragraph("CITIZEN GRIEVANCE ACKNOWLEDGEMENT RECEIPT", styles['DocTitle'])]],
                        colWidths=[17 * cm],
                        style=TableStyle([
                            ('BACKGROUND', (0, 0), (-1, -1), NAVY),
                            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                        ])))
    story.append(Spacer(1, 0.4 * cm))

    # -------------------------------------------------- tracking number box
    tracking_box = Table(
        [[Paragraph("COMPLAINT / TRACKING NUMBER", ParagraphStyle(
            'tnlabel', fontName='Helvetica-Bold', fontSize=8.5, textColor=GOLD, alignment=TA_CENTER))],
         [Paragraph(issue.tracking_number, ParagraphStyle(
             'tnvalue', fontName='Helvetica-Bold', fontSize=20, textColor=NAVY, alignment=TA_CENTER))]],
        colWidths=[17 * cm],
        style=TableStyle([
            ('BOX', (0, 0), (-1, -1), 1.2, GOLD),
            ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
            ('TOPPADDING', (0, 0), (-1, 0), 6), ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
            ('TOPPADDING', (0, 1), (-1, 1), 2), ('BOTTOMPADDING', (0, 1), (-1, 1), 8),
        ])
    )
    story.append(tracking_box)
    story.append(Spacer(1, 0.4 * cm))

    # -------------------------------------------------------- details grid
    def field(label, value):
        return [Paragraph(label.upper(), styles['FieldLabel']), Paragraph(str(value) if value else '—', styles['FieldValue'])]

    left_col = [
        field("Complaint Title", issue.title),
        field("Category", issue.category.name if issue.category else '—'),
        field("Priority", issue.get_priority_display()),
        field("Reported By", issue.display_reporter_name),
    ]
    right_col = [
        field("Status", issue.get_status_display()),
        field("Department", issue.department.name if issue.department else 'Not yet assigned'),
        field("Officer In-Charge", issue.assigned_officer.username if issue.assigned_officer else 'Not yet assigned'),
        field("Date &amp; Time of Report", issue.created_at.strftime('%d-%m-%Y %I:%M %p')),
    ]

    grid_rows = []
    for l, r in zip(left_col, right_col):
        grid_rows.append([l[0], l[1], r[0], r[1]])
    details_table = Table(grid_rows, colWidths=[3.3 * cm, 5.2 * cm, 3.3 * cm, 5.2 * cm])
    details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor('#E3E8EE')),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 0.3 * cm))

    # ------------------------------------------------------------ location
    loc_table = Table([[
        field("Address / Landmark", issue.address or 'See coordinates')[0],
        field("Address / Landmark", issue.address or 'See coordinates')[1],
        field("GPS Coordinates", f"{issue.latitude:.5f}, {issue.longitude:.5f}")[0],
        field("GPS Coordinates", f"{issue.latitude:.5f}, {issue.longitude:.5f}")[1],
    ]], colWidths=[3.3 * cm, 5.2 * cm, 3.3 * cm, 5.2 * cm])
    loc_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor('#E3E8EE')),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(loc_table)
    story.append(Spacer(1, 0.5 * cm))

    # -------------------------------------------------------- description
    story.append(Paragraph("COMPLAINT DESCRIPTION", styles['SectionHeading']))
    desc_box = Table([[Paragraph(issue.description, styles['BodyText9'])]], colWidths=[17 * cm])
    desc_box.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#E3E8EE')),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(desc_box)
    story.append(Spacer(1, 0.5 * cm))

    # ------------------------------------------------------------- QR + note
    qr_buf = _generate_qr_image(request, issue)
    qr_flowable = RLImage(qr_buf, width=2.6 * cm, height=2.6 * cm) if qr_buf else Spacer(2.6 * cm, 2.6 * cm)
    note_text = Paragraph(
        f"Scan the QR code to track live status of this complaint online, or visit "
        f"<b>{request.build_absolute_uri(issue.get_absolute_url())}</b>. "
        f"Please quote the tracking number <b>{issue.tracking_number}</b> in all future correspondence "
        f"regarding this complaint.", styles['BodyText9']
    )
    qr_row = Table([[qr_flowable, note_text]], colWidths=[3 * cm, 14 * cm])
    qr_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    story.append(qr_row)
    story.append(Spacer(1, 0.6 * cm))

    # --------------------------------------------------------------- footer
    story.append(Table([['']], colWidths=[17 * cm], rowHeights=[0.02 * cm],
                        style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E3E8EE'))])))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "This is a computer-generated acknowledgement receipt and does not require a physical signature or seal. "
        "For emergency assistance, call 108 (Ambulance) / 101 (Fire) / 100 (Police).",
        styles['Disclaimer']
    ))
    story.append(Paragraph(
        f"Generated by Kuraigal.TN on {issue.created_at.strftime('%d-%m-%Y')} — Government Smart City Citizen Grievance Management Portal",
        styles['Disclaimer']
    ))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
        title=f"Complaint Receipt - {issue.tracking_number}",
    )
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def issue_pdf(request, pk):
    """Export a single issue as PDF, with an embedded QR code linking back to the issue."""
    issue = get_object_or_404(Issue, pk=pk)
    try:
        pdf_bytes = _build_issue_pdf_bytes(request, issue)
    except ImportError:
        return HttpResponse(
            "PDF export requires the 'reportlab' package. Install it with: pip install reportlab",
            status=500, content_type='text/plain'
        )
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="issue_{issue.pk}.pdf"'
    return response


def send_report_confirmation_email(request, issue):
    """Emails the citizen their complaint PDF + an acceptance message, from the
    government address configured in DEFAULT_FROM_EMAIL. Never raises - a failed
    email should never break the report submission itself."""
    if not issue.reporter_email:
        return False
    try:
        from django.core.mail import EmailMessage
        pdf_bytes = _build_issue_pdf_bytes(request, issue)

        subject = f"Your complaint has been received - {issue.tracking_number}"
        body = (
            f"Dear Citizen,\n\n"
            f"Your complaint has been successfully received by Kuraigal.TN.\n\n"
            f"Tracking Number : {issue.tracking_number}\n"
            f"Title           : {issue.title}\n"
            f"Category        : {issue.category.name if issue.category else '-'}\n"
            f"Status          : {issue.get_status_display()}\n"
            f"Reported At     : {issue.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"You can track live updates here:\n{request.build_absolute_uri(issue.get_absolute_url())}\n\n"
            f"A copy of your complaint is attached as a PDF for your records.\n\n"
            f"Thank you for helping us build a better neighborhood.\n\n"
            f"- Kuraigal.TN, Government Smart City Grievance Portal"
        )
        email = EmailMessage(subject=subject, body=body, to=[issue.reporter_email])
        email.attach(f"{issue.tracking_number}.pdf", pdf_bytes, 'application/pdf')
        email.send(fail_silently=False)
        return True
    except Exception as e:
        # Log to the console so it's visible in runserver output, but never break the request.
        print(f"[email] Failed to send confirmation email for issue {issue.pk}: {e}")
        return False


def _generate_qr_image(request, issue):
    """Returns an in-memory PNG (BytesIO) of a QR code pointing to the issue's page, or None if
    the 'qrcode' package isn't installed."""
    try:
        import qrcode
        import io
    except ImportError:
        return None
    url = request.build_absolute_uri(issue.get_absolute_url())
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0b2545", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


def issue_qr_code(request, pk):
    """Standalone QR code PNG for an issue - scanning it opens the issue's public page."""
    issue = get_object_or_404(Issue, pk=pk)
    buf = _generate_qr_image(request, issue)
    if buf is None:
        return HttpResponse(
            "QR code generation requires the 'qrcode' package. Install it with: pip install qrcode",
            status=500, content_type='text/plain'
        )
    return HttpResponse(buf.getvalue(), content_type='image/png')


# ------------------------------------------------------------- notifications
@login_required
def notifications_view(request):
    notifications = request.user.notifications.all()
    notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'issues/notifications.html', {'notifications': notifications})


@login_required
def notifications_poll(request):
    """Lightweight JSON endpoint the browser polls to power local notification alerts
    (Phase 8). Does NOT mark anything as read - that only happens on the full page."""
    unread = request.user.notifications.filter(is_read=False).order_by('-created_at')[:5]
    return JsonResponse({
        'count': request.user.notifications.filter(is_read=False).count(),
        'latest': [{'id': n.id, 'message': n.message} for n in unread],
    })


# ------------------------------------------------------- leaderboard/profile
def leaderboard_view(request):
    board_type = request.GET.get('type', 'citizens')

    officers = None
    if board_type == 'officers':
        officers = (User.objects.filter(is_staff=True)
                    .annotate(
                        resolved_count=Count('assigned_issues', filter=Q(assigned_issues__status='resolved'), distinct=True),
                        avg_rating=Avg('ratings_received__stars'),
                        rating_count=Count('ratings_received', distinct=True),
                    )
                    .filter(resolved_count__gt=0)
                    .order_by('-resolved_count', '-avg_rating'))

    profiles = UserProfile.objects.select_related('user').order_by('-points')[:20]
    return render(request, 'issues/leaderboard.html', {
        'profiles': profiles,
        'officers': officers,
        'board_type': board_type,
    })


@login_required
def my_profile_view(request):
    profile, _created = UserProfile.objects.get_or_create(user=request.user)
    my_issues = Issue.objects.filter(reported_by=request.user).annotate(votes=Count('upvotes'))

    dashboard_stats = {
        'total': my_issues.count(),
        'open': my_issues.filter(status='open').count(),
        'in_progress': my_issues.filter(status='in_progress').count(),
        'resolved': my_issues.filter(status='resolved').count(),
        'bookmarks': request.user.bookmarked_issues.count(),
    }

    context = {
        'profile': profile,
        'my_issues': my_issues.order_by('-created_at')[:9],
        'dashboard_stats': dashboard_stats,
        'reputation': profile.reputation_level(),
        'is_volunteer': Volunteer.objects.filter(user=request.user, is_active=True).exists(),
    }
    return render(request, 'issues/profile.html', context)


# --------------------------------------------------------------------- auth
def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, _("Welcome! Your account has been created."))
            return redirect('issue_list')
    else:
        form = SignUpForm()
    return render(request, 'issues/signup.html', {'form': form})


MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300  # 5 minutes


class ThrottledLoginView(auth_views.LoginView):
    """Login view with basic brute-force protection: after 5 failed attempts
    from the same IP, further tries are blocked for 5 minutes. Uses Django's
    cache framework so it needs no extra database table or dependency."""
    template_name = 'issues/login.html'

    def _client_ip(self):
        forwarded = self.request.META.get('HTTP_X_FORWARDED_FOR', '')
        return forwarded.split(',')[0].strip() or self.request.META.get('REMOTE_ADDR', 'unknown')

    def dispatch(self, request, *args, **kwargs):
        self._throttle_key = f'login_attempts_{self._client_ip()}'
        if cache.get(self._throttle_key, 0) >= MAX_LOGIN_ATTEMPTS:
            messages.error(request, _("Too many failed login attempts. Please try again in a few minutes."))
            return redirect('login')
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        attempts = cache.get(self._throttle_key, 0) + 1
        cache.set(self._throttle_key, attempts, LOGIN_LOCKOUT_SECONDS)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._throttle_key)
        user = form.get_user()
        if user.is_staff:
            AuditLog.log(user, 'login', detail='Staff login', request=self.request)
        return super().form_valid(form)


# --------------------------------------------------------------- volunteer
@login_required
def volunteer_view(request):
    volunteer = Volunteer.objects.filter(user=request.user).first()

    if request.method == 'POST':
        interests = request.POST.get('interests', '').strip()
        phone = request.POST.get('phone', '').strip()
        availability = request.POST.get('availability', 'anytime')

        if volunteer:
            volunteer.interests = interests
            volunteer.phone = phone
            volunteer.availability = availability
            volunteer.is_active = True
            volunteer.save()
            messages.success(request, _("Your volunteer details have been updated."))
        else:
            Volunteer.objects.create(
                user=request.user, interests=interests, phone=phone, availability=availability
            )
            profile, _created = UserProfile.objects.get_or_create(user=request.user)
            profile.add_points(15)
            messages.success(request, _("Thanks for volunteering! The community appreciates it."))
        return redirect('volunteer')

    return render(request, 'issues/volunteer.html', {
        'volunteer': volunteer,
        'availability_choices': Volunteer.AVAILABILITY_CHOICES,
    })


@login_required
def volunteer_unregister(request):
    if request.method == 'POST':
        Volunteer.objects.filter(user=request.user).delete()
        messages.success(request, _("You've been removed from the volunteer list."))
    return redirect('volunteer')


# ---------------------------------------------------------------- feedback
@login_required
def feedback_view(request):
    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        message_text = request.POST.get('message', '').strip()
        feedback_type = request.POST.get('feedback_type', 'suggestion')

        if subject and message_text and not is_spam_text(message_text, min_words=3):
            Feedback.objects.create(
                user=request.user, feedback_type=feedback_type, subject=subject, message=message_text
            )
            messages.success(request, _("Thank you for your feedback! Our team will review it."))
            return redirect('feedback')
        else:
            messages.error(request, _("Please provide a valid subject and message."))

    my_feedback = Feedback.objects.filter(user=request.user)[:10]
    return render(request, 'issues/feedback.html', {
        'feedback_type_choices': Feedback.FEEDBACK_TYPE_CHOICES,
        'my_feedback': my_feedback,
    })


# --------------------------------------------------------------------- pwa
def service_worker_view(request):
    """Serves the service worker from the site ROOT (not /static/) so its scope
    covers the whole app - browsers only let a SW control pages at or below
    the path it's served from."""
    from django.conf import settings
    import os
    sw_path = os.path.join(settings.BASE_DIR, 'static', 'service-worker.js')
    try:
        with open(sw_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        content = ''
    return HttpResponse(content, content_type='application/javascript')


# ------------------------------------------------------------------ chatbot
def chatbot_view(request):
    """AJAX endpoint for the floating AI Chatbot widget (see base.html).
    Checks for live-data / personalized questions first (real DB queries),
    then falls back to the static keyword corpus in issues/ai.py."""
    message = request.POST.get('message', '') or request.GET.get('message', '')
    text_lower = message.lower()

    # ---- Personalized (requires login) ----
    if request.user.is_authenticated:
        if any(kw in text_lower for kw in ['my point', 'my score', 'enakku evlo point', 'points evlo', 'en points']):
            profile, _c = UserProfile.objects.get_or_create(user=request.user)
            badge = profile.badge()
            return JsonResponse({'reply': (
                f"You have {profile.points} community points and hold the '{badge[1]}' badge. "
                f"Keep reporting and helping others to earn more!"
            )})
        if any(kw in text_lower for kw in ['my issue', 'my report', 'my complaint', 'en issue', 'naan report', 'en complaint']):
            my_issues = Issue.objects.filter(reported_by=request.user)
            total = my_issues.count()
            resolved = my_issues.filter(status='resolved').count()
            open_count = my_issues.exclude(status='resolved').count()
            if total == 0:
                return JsonResponse({'reply': "You haven't reported any issues yet - tap the '+' button to report your first one!"})
            return JsonResponse({'reply': (
                f"You've reported {total} issue(s): {resolved} resolved, {open_count} still open. "
                f"Check 'My Profile' for the full list."
            )})
        if any(kw in text_lower for kw in ['my bookmark', 'en bookmark']):
            count = request.user.bookmarked_issues.count()
            return JsonResponse({'reply': f"You have {count} bookmarked issue(s). Find them under 'My Bookmarks'."})

    # ---- Live city-wide data (no login needed) ----
    if any(kw in text_lower for kw in ['how many open', 'open issues', 'total complaints', 'total issues',
                                        'evlo issues', 'evlo complaints', 'total evlo', 'ethana issues',
                                        'ethana complaints']):
        total = Issue.objects.count()
        open_count = Issue.objects.exclude(status='resolved').count()
        return JsonResponse({'reply': f"There are {total} total complaints reported so far, {open_count} of them still open."})

    if any(kw in text_lower for kw in ['how many emergenc', 'active emergenc', 'emergency now', 'emergencies right now',
                                        'evlo emergency', 'ippo emergency', 'emergency evlo']):
        active = Issue.objects.filter(is_emergency=True).exclude(status='resolved').count()
        if active:
            return JsonResponse({'reply': f"There are currently {active} active emergency report(s). Check the Emergency Dashboard for live details."})
        return JsonResponse({'reply': "There are no active emergencies right now. Stay safe!"})

    if any(kw in text_lower for kw in ['resolution rate', 'how many resolved', 'evlo resolve', 'resolve aana evlo',
                                        'ethana resolve']):
        total = Issue.objects.count()
        resolved = Issue.objects.filter(status='resolved').count()
        rate = round((resolved / total) * 100, 1) if total else 0
        return JsonResponse({'reply': f"{resolved} out of {total} complaints have been resolved so far - a {rate}% resolution rate."})

    # ---- Static keyword-matched corpus (issues/ai.py) ----
    reply = chatbot_reply(message)
    return JsonResponse({'reply': reply})
