from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('service-worker.js', views.service_worker_view, name='service_worker'),
    path('issues/', views.issue_list, name='issue_list'),
    path('issues/map-data/', views.issue_map_data, name='issue_map_data'),
    path('issue/<int:pk>/', views.issue_detail, name='issue_detail'),
    path('issue/<int:pk>/pdf/', views.issue_pdf, name='issue_pdf'),
    path('issue/<int:pk>/qr/', views.issue_qr_code, name='issue_qr'),
    path('report/', views.report_issue, name='report_issue'),
    path('check-duplicate/', views.check_duplicate, name='check_duplicate'),
    path('ai-suggest/', views.ai_suggest_view, name='ai_suggest'),
    path('issue/<int:pk>/upvote/', views.toggle_upvote, name='toggle_upvote'),
    path('issue/<int:pk>/bookmark/', views.toggle_bookmark, name='toggle_bookmark'),
    path('issue/<int:pk>/status/', views.update_status, name='update_status'),
    path('issue/<int:pk>/assign-officer/', views.assign_officer, name='assign_officer'),
    path('issue/<int:pk>/assign-department/', views.assign_department, name='assign_department'),

    path('comment/<int:pk>/like/', views.toggle_comment_like, name='toggle_comment_like'),
    path('comment/<int:pk>/edit/', views.edit_comment, name='edit_comment'),
    path('comment/<int:pk>/delete/', views.delete_comment, name='delete_comment'),

    path('issue/<int:pk>/rate-officer/', views.rate_officer, name='rate_officer'),

    path('heatmap/', views.heatmap_view, name='heatmap'),
    path('heatmap-data/', views.heatmap_data, name='heatmap_data'),
    path('nearby/', views.nearby_issues_view, name='nearby_issues'),

    path('departments/', views.department_list_view, name='departments'),
    path('emergency/', views.emergency_dashboard, name='emergency_dashboard'),

    path('analytics/', views.analytics_dashboard, name='analytics'),
    path('analytics/pdf/', views.analytics_pdf, name='analytics_pdf'),
    path('issues/export-csv/', views.export_issues_csv, name='export_issues_csv'),

    path('notifications/', views.notifications_view, name='notifications'),
    path('notifications/poll/', views.notifications_poll, name='notifications_poll'),
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
    path('profile/', views.my_profile_view, name='my_profile'),
    path('bookmarks/', views.my_bookmarks_view, name='my_bookmarks'),

    path('volunteer/', views.volunteer_view, name='volunteer'),
    path('volunteer/unregister/', views.volunteer_unregister, name='volunteer_unregister'),
    path('feedback/', views.feedback_view, name='feedback'),

    path('officer/', views.officer_dashboard, name='officer_dashboard'),
    path('officer/issue/<int:pk>/update/', views.officer_update, name='officer_update'),
    path('activity-log/', views.activity_log_view, name='activity_log'),

    path('chatbot/', views.chatbot_view, name='chatbot'),

    path('signup/', views.signup, name='signup'),
    path('login/', views.ThrottledLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
