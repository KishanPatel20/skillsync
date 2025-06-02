from django.urls import path
from . import b_views

urlpatterns = [
    # Company Management
    path('skillsync/companies/', b_views.company_list_create, name='company-list-create'),

    # Authentication
    path('skillsync/hr/register/', b_views.register_user, name='hr-register'),
    path('skillsync/hr/login/', b_views.login_user, name='hr-login'),
    path('skillsync/hr/logout/', b_views.logout_user, name='hr-logout'),

    # Candidate Management
    path('skillsync/candidates/', b_views.CandidateListCreateView.as_view(), name='candidate-list-create'),
    path('skillsync/candidates/<int:pk>/', b_views.candidate_detail_update_status, name='candidate-detail-update'),

    # Resume & Profile Management
    path('skillsync/resume/upload/', b_views.upload_resume_api, name='resume-upload'),
    path('skillsync/linkedin/search/', b_views.linkedin_search_api, name='linkedin-search'),
    path('skillsync/linkedin/profile/', b_views.scrape_and_analyze_linkedin_profile_api, name='linkedin-profile-scrape'),

    # Dashboard & Search
    path('skillsync/dashboard/', b_views.hr_dashboard_summary, name='hr-dashboard'),
    # path('skillsync/search/candidates/', b_views.search_candidates_by_jd, name='search-candidates'),

    # AI Analysis
    path('skillsync/analysis/generate/', b_views.generate_candidate_analysis, name='generate-candidate-analysis'),
]