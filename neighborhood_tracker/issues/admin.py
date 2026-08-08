from django.contrib import admin
from .models import Department, Category, Issue, Comment, IssueStatusHistory, Notification, UserProfile, OfficerRating, Volunteer, Feedback, AuditLog

admin.site.site_header = "Kuraigal.TN Administration"
admin.site.site_title = "Kuraigal.TN Admin"
admin.site.index_title = "Government Smart City Grievance Portal - Admin Dashboard"


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('actor', 'action', 'issue', 'detail', 'ip_address', 'created_at')
    list_filter = ('action',)
    readonly_fields = ('actor', 'action', 'issue', 'detail', 'ip_address', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'contact_phone', 'contact_email', 'total_issue_count', 'resolution_rate')
    search_fields = ('name',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'department')
    list_filter = ('department',)


class HistoryInline(admin.TabularInline):
    model = IssueStatusHistory
    extra = 0
    readonly_fields = ('status', 'changed_by', 'note', 'created_at')


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'department', 'ward', 'assigned_officer', 'priority', 'status', 'is_emergency', 'escalated', 'is_anonymous', 'reported_by', 'upvote_count', 'bookmark_count', 'created_at')
    list_filter = ('status', 'category', 'department', 'priority', 'is_emergency', 'emergency_type', 'escalated', 'is_anonymous')
    search_fields = ('title', 'description', 'address', 'reporter_email', 'ward')
    list_editable = ('status', 'priority', 'is_emergency')
    inlines = [HistoryInline]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('issue', 'user', 'like_count', 'is_edited', 'created_at')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'is_read', 'created_at')
    list_filter = ('is_read',)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'points', 'is_officer', 'department')
    list_filter = ('is_officer', 'department')
    list_editable = ('is_officer', 'department')


@admin.register(OfficerRating)
class OfficerRatingAdmin(admin.ModelAdmin):
    list_display = ('officer', 'issue', 'stars', 'rated_by', 'created_at')
    list_filter = ('stars',)


@admin.register(Volunteer)
class VolunteerAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'availability', 'is_active', 'registered_at')
    list_filter = ('availability', 'is_active')
    list_editable = ('is_active',)


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('subject', 'feedback_type', 'user', 'is_reviewed', 'created_at')
    list_filter = ('feedback_type', 'is_reviewed')
    list_editable = ('is_reviewed',)
