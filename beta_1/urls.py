from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import (
    ResumeUploadView, CandidateDetailView, CandidateResumeView, CandidateSearchView, CandidateSummaryView
)

# If you are not using any ViewSets, you can remove the router lines below.
# If you want to use router, define it and register viewsets as needed.
# For now, just remove the router usage to fix the error.

urlpatterns = [
    path('skillsync/candidates/upload-resume/', ResumeUploadView.as_view(), name='upload-resume'),
    path('skillsync/candidates/<int:candidate_id>/', CandidateDetailView.as_view(), name='candidate-detail'),
    path('skillsync/candidates/<int:candidate_id>/resume/', CandidateResumeView.as_view(), name='candidate-resume'),
    path('skillsync/candidates/search/', CandidateSearchView.as_view(), name='candidate-search'),
    path('skillsync/candidates/<int:candidate_id>/summary/', CandidateSummaryView.as_view(), name='candidate-summary'),
]