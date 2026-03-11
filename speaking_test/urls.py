from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('register/pending/', views.register_pending, name='register_pending'),
    path('access-denied/<str:reason>/', views.access_denied, name='access_denied'),
    path('outsider/', views.outsider_entry, name='outsider_entry'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('test/select/', views.test_select, name='test_select'),
    # part: 1.1 / 1.2 / 2 / 3 / full
    path('test/start/<str:part>/', views.test_start_part, name='test_start_part'),
    path('test/session/<uuid:session_id>/', views.test_session, name='test_session'),
    path('test/complete/<uuid:session_id>/', views.test_complete, name='test_complete'),
    path('test/results/<uuid:session_id>/', views.test_results, name='test_results'),
    path('api/submit-response/', views.api_submit_response, name='api_submit_response'),
    path('api/session-status/<uuid:session_id>/', views.api_session_status, name='api_session_status'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('progress/', views.student_progress, name='student_progress'),
    path('teacher/', views.teacher_panel, name='teacher_panel'),
    path('analytics/', views.admin_analytics, name='admin_analytics'),
    path('api/dismiss-announcement/<int:ann_id>/', views.dismiss_announcement, name='dismiss_announcement'),
    path('writing/', views.writing_check, name='writing_check'),
    path('api/live-count/', views.api_live_count, name='api_live_count'),
]
