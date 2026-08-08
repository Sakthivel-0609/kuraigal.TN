from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
import math


class Department(models.Model):
    """Government department that handles a group of complaint categories,
    e.g. Water Supply, Electricity Board, Road Department."""
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Emoji or icon class")
    description = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def open_issue_count(self):
        return self.issues.exclude(status='resolved').count()

    def resolved_issue_count(self):
        return self.issues.filter(status='resolved').count()

    def total_issue_count(self):
        return self.issues.count()

    def resolution_rate(self):
        total = self.total_issue_count()
        return round((self.resolved_issue_count() / total) * 100, 1) if total else 0


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Emoji or icon class, e.g. 🕳️")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='categories')

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class Issue(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('emergency', 'Emergency'),
    ]

    EMERGENCY_TYPE_CHOICES = [
        ('fire', '🔥 Fire'),
        ('flood', '🌊 Flood'),
        ('road_accident', '🚗 Road Accident'),
        ('gas_leak', '⛽ Gas Leak'),
        ('electric_shock', '⚡ Electric Shock'),
        ('water_leakage', '💧 Water Leakage'),
        ('building_collapse', '🏚️ Building Collapse'),
        ('tree_fallen', '🌳 Tree Fallen'),
        ('medical_emergency', '🚑 Medical Emergency'),
        ('other', '❗ Other Emergency'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='issues')
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='issues',
        help_text="Auto-filled from the category's department; staff can reassign."
    )
    reported_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reported_issues')
    reporter_email = models.EmailField(
        blank=True,
        help_text="Optional - if provided, a confirmation email with the complaint PDF is sent here."
    )
    is_anonymous = models.BooleanField(
        default=False,
        help_text="If checked, the reporter's name is hidden from public view (staff can still see it)."
    )
    ward = models.CharField(max_length=50, blank=True, help_text="Ward or zone number/name, e.g. 'Ward 12'.")
    assigned_officer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_issues',
        limit_choices_to={'is_staff': True}, help_text="Officer responsible for resolving this complaint."
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    address = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(
        max_length=20, choices=PRIORITY_CHOICES, default='medium',
        help_text="Auto-assigned by AI priority detection based on the description; staff can override."
    )
    is_emergency = models.BooleanField(default=False, help_text="Mark if this is dangerous / needs urgent attention")
    emergency_type = models.CharField(
        max_length=30, choices=EMERGENCY_TYPE_CHOICES, blank=True,
        help_text="Specific emergency category - required when 'is_emergency' is checked."
    )
    escalated = models.BooleanField(default=False, help_text="Auto-set when an open issue exceeds the SLA window without action.")
    escalated_at = models.DateTimeField(null=True, blank=True)
    upvotes = models.ManyToManyField(User, related_name='upvoted_issues', blank=True)
    bookmarks = models.ManyToManyField(User, related_name='bookmarked_issues', blank=True)
    image = models.ImageField(upload_to='issue_images/', blank=True, null=True, help_text="Photo taken when the issue was reported ('before').")
    completion_image = models.ImageField(
        upload_to='completion_images/', blank=True, null=True,
        help_text="Photo uploaded by the officer after fixing the issue ('after') - powers the Before/After comparison."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_emergency', '-created_at']
        indexes = [
            models.Index(fields=['-is_emergency', '-created_at'], name='idx_issue_emergency_created'),
            models.Index(fields=['status'], name='idx_issue_status'),
            models.Index(fields=['priority'], name='idx_issue_priority'),
            models.Index(fields=['category'], name='idx_issue_category'),
            models.Index(fields=['department'], name='idx_issue_department'),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Auto-fill department from the category the first time this issue is saved,
        # unless staff has already explicitly assigned a different department.
        if not self.department_id and self.category_id and self.category.department_id:
            self.department_id = self.category.department_id
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('issue_detail', args=[self.pk])

    def upvote_count(self):
        return self.upvotes.count()

    def bookmark_count(self):
        return self.bookmarks.count()

    @property
    def tracking_number(self):
        """Government-style complaint tracking number, e.g. NT-2026-000042.
        Derived from existing fields only - no schema change required."""
        year = self.created_at.year if self.created_at else timezone.now().year
        return f"NT-{year}-{self.pk:06d}"

    @property
    def ai_summary(self):
        """Short AI-generated summary of a long description, for quick scanning
        on cards and the department dashboard. Only meaningfully different from
        the full description when it's long, so callers should check length first."""
        from .ai import generate_summary
        return generate_summary(self.description)

    @property
    def display_reporter_name(self):
        """Public-facing reporter name - hides the real username when the citizen
        chose to report anonymously. Staff should use issue.reported_by.username
        directly (e.g. in the admin panel) where accountability is required."""
        if self.is_anonymous:
            return "Anonymous Citizen"
        return self.reported_by.username

    def distance_to(self, lat, lng):
        """Haversine distance in meters between this issue and given coordinates."""
        R = 6371000
        phi1, phi2 = math.radians(self.latitude), math.radians(lat)
        dphi = math.radians(lat - self.latitude)
        dlambda = math.radians(lng - self.longitude)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))


class Comment(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    likes = models.ManyToManyField(User, related_name='liked_comments', blank=True)
    is_edited = models.BooleanField(default=False)
    is_flagged_spam = models.BooleanField(default=False, help_text="Set by the AI spam filter when the comment was blocked.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.user} on {self.issue}"

    def like_count(self):
        return self.likes.count()


class IssueStatusHistory(models.Model):
    """Timeline entries: every status change / creation event for an issue."""
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='history')
    status = models.CharField(max_length=20, choices=Issue.STATUS_CHOICES)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = "Issue status histories"

    def __str__(self):
        return f"{self.issue.title} -> {self.status}"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"To {self.user}: {self.message}"


BADGE_THRESHOLDS = [
    (0, 'Newcomer', '🌱'),
    (20, 'Bronze Reporter', '🥉'),
    (75, 'Silver Reporter', '🥈'),
    (200, 'Gold Reporter', '🥇'),
    (500, 'Community Champion', '🏆'),
]


class OfficerRating(models.Model):
    """Citizen rating (1-5 stars) for the officer who handled a resolved complaint.
    One rating per issue, given by the citizen who reported it."""
    issue = models.OneToOneField(Issue, on_delete=models.CASCADE, related_name='officer_rating')
    officer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings_received')
    rated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings_given')
    stars = models.PositiveSmallIntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    comment = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stars}★ for {self.officer} on {self.issue}"


class Volunteer(models.Model):
    """Citizen registration to volunteer for community civic drives
    (cleanup campaigns, tree plantation, awareness drives, etc.)."""
    AVAILABILITY_CHOICES = [
        ('weekdays', 'Weekdays'),
        ('weekends', 'Weekends'),
        ('anytime', 'Anytime'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='volunteer_profile')
    phone = models.CharField(max_length=20, blank=True)
    interests = models.CharField(max_length=255, help_text="e.g. Cleanup drives, Tree plantation, Awareness campaigns")
    availability = models.CharField(max_length=20, choices=AVAILABILITY_CHOICES, default='anytime')
    is_active = models.BooleanField(default=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Volunteer: {self.user.username}"


class Feedback(models.Model):
    """General citizen feedback / suggestion to the portal, not tied to a specific issue."""
    FEEDBACK_TYPE_CHOICES = [
        ('suggestion', 'Suggestion'),
        ('complaint', 'Complaint about the Portal'),
        ('appreciation', 'Appreciation'),
        ('other', 'Other'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedback_submitted')
    feedback_type = models.CharField(max_length=20, choices=FEEDBACK_TYPE_CHOICES, default='suggestion')
    subject = models.CharField(max_length=150)
    message = models.TextField()
    is_reviewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_feedback_type_display()}: {self.subject}"


class AuditLog(models.Model):
    """Append-only record of staff/admin actions for accountability - who did
    what, when. Read-only in the admin panel; never edited or deleted from the UI."""
    ACTION_CHOICES = [
        ('status_change', 'Status Changed'),
        ('officer_assigned', 'Officer Assigned'),
        ('department_reassigned', 'Department Reassigned'),
        ('comment_deleted', 'Comment Deleted'),
        ('officer_flag_changed', 'Officer Flag Changed'),
        ('login', 'Staff Login'),
        ('other', 'Other'),
    ]
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_actions')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    issue = models.ForeignKey(Issue, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    detail = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.actor}: {self.get_action_display()} @ {self.created_at:%Y-%m-%d %H:%M}"

    @staticmethod
    def log(actor, action, issue=None, detail='', request=None):
        ip = None
        if request is not None:
            ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
        AuditLog.objects.create(actor=actor, action=action, issue=issue, detail=detail[:255], ip_address=ip or None)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    points = models.PositiveIntegerField(default=0)
    is_officer = models.BooleanField(default=False, help_text="Officers see the Officer Dashboard with complaints assigned to them.")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='officers')

    def __str__(self):
        return f"{self.user.username} ({self.points} pts)"

    def badge(self):
        current = BADGE_THRESHOLDS[0]
        for threshold in BADGE_THRESHOLDS:
            if self.points >= threshold[0]:
                current = threshold
        return current  # (points_needed, name, emoji)

    def next_badge(self):
        for threshold in BADGE_THRESHOLDS:
            if self.points < threshold[0]:
                return threshold
        return None

    def add_points(self, amount):
        self.points += amount
        self.save(update_fields=['points'])

    def reputation_level(self):
        """Trust tier computed from existing data (reports + resolution rate) -
        no extra field needed, always reflects current activity."""
        reports = self.user.reported_issues.all()
        total = reports.count()
        if total < 3:
            return ('New Reporter', '🌱')
        resolved = reports.filter(status='resolved').count()
        rate = resolved / total
        if rate >= 0.7 and total >= 10:
            return ('Highly Trusted', '💎')
        if rate >= 0.5:
            return ('Trusted Reporter', '✅')
        return ('Active Reporter', '📍')


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=Issue)
def create_history_on_issue_create(sender, instance, created, **kwargs):
    if created:
        IssueStatusHistory.objects.create(issue=instance, status=instance.status, changed_by=instance.reported_by, note="Issue reported")
        profile, _ = UserProfile.objects.get_or_create(user=instance.reported_by)
        profile.add_points(10)
