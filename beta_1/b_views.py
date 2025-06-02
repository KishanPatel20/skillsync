import json
import os
import requests # Assuming you'll use requests for external API calls
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import IntegrityError # For handling unique_together errors
from dateutil import parser

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView # For class-based views (optional, but good for list/detail)

# Import your models
from .models import (
    Company, HRProfile, Candidate, Experience, Skill,
    CandidateSkill, Project, AISummary, ActivityLog,
    LinkedInProfile, CandidateStatusLog
)

# Import your serializers (You'll need to define these in serializers.py)
from .serializers import (
    CompanySerializer, UserRegistrationSerializer, AuthTokenSerializer,
    CandidateSerializer, AISummarySerializer, CandidateStatusLogSerializer
)

# Import your custom permissions
from .permissions import IsCompanyUser

# Import your logic functions (ensure these exist in your logic.py)
# from .logic import (
#     extract_resume_details, # To parse uploaded resume
#     get_candidate_scores_from_llm, # To get overall scores (might be modified)
#     extract_jd_requirements, # To parse JD content
#     score_candidate # To score a candidate against a JD
#     # You might also need a function to generate Google queries for Serper.dev
#     # and a function to parse scraped LinkedIn data into Candidate-like structure
# )

# Import your AI analysis functions (ensure these exist in your b_resume_rank.py)
from .b_resume_rank import get_candidate_analysis

# --- Company Management Views ---
# Accessible by admin or specific roles to create/list companies
@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsAdminUser]) # Only admins can manage companies for now
def company_list_create(request):
    """
    List all companies or create a new company.
    Requires admin privileges.
    """
    if request.method == 'GET':
        companies = Company.objects.all()
        serializer = CompanySerializer(companies, many=True)
        return Response(serializer.data)
    elif request.method == 'POST':
        serializer = CompanySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# --- Authentication Views ---

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    """
    Register a new HR user and create/update company details.
    Required fields:
    - username
    - email
    - password
    - company_name
    - company_size (optional)
    - company_website (optional)
    - company_linkedin_url (optional)
    - company_location (optional)
    """
    try:
        # First create/update company
        company_data = {
            'name': request.data.get('company_name'),
            'size': request.data.get('company_size'),
            'website': request.data.get('company_website'),
            'linkedin_url': request.data.get('company_linkedin_url'),
            'location': request.data.get('company_location')
        }
        
        company_serializer = CompanySerializer(data=company_data)
        if company_serializer.is_valid():
            company = company_serializer.save()
        else:
            return Response(company_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Now create user with company
        user_data = {
            'username': request.data.get('username'),
            'email': request.data.get('email'),
            'password': request.data.get('password'),
            'company_id': company.id
        }
        
        serializer = UserRegistrationSerializer(data=user_data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Create token for the new user
            token, _ = Token.objects.get_or_create(user=user)
            
            # Log registration activity
            ActivityLog.objects.create(
                user=user,
                company=company,
                activity_type='REGISTER',
                details_json={
                    'new_user_id': user.id,
                    'company_id': company.id,
                    'company_name': company.name
                }
            )
            
            return Response({
                'message': 'User registered successfully',
                'token': token.key,
                'username': user.username,
                'user_id': user.id,
                'company_id': company.id,
                'company_name': company.name
            }, status=status.HTTP_201_CREATED)
        else:
            # If user creation fails, delete the company
            company.delete()
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
    except IntegrityError:
        return Response({'error': 'Username or email already exists'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': f'Registration failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny]) # Allow anyone to attempt login
def login_user(request):
    """
    Authenticate an HR user and return an auth token.
    """
    serializer = AuthTokenSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data['user']
    token, created = Token.objects.get_or_create(user=user)
    login(request, user) # Use Django's session login as well (optional but good for browsable API)

    # Log login activity
    company = user.hr_profile.company if hasattr(user, 'hr_profile') else None
    if company:
        ActivityLog.objects.create(
            user=user,
            company=company,
            activity_type='LOGIN',
            details_json={'username': user.username, 'company_id': company.id}
        )
        return Response({'token': token.key, 'username': user.username, 'user_id': user.id, 'company_id': company.id})
    else:
        # Handle case where HRProfile might not exist (e.g., admin user)
        # For this system, all HRs should have a profile.
        return Response({'error': 'User profile not associated with a company.'}, status=status.HTTP_403_FORBIDDEN)


@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated]) # Only authenticated users can logout
def logout_user(request):
    """
    Log out an HR user, deleting their auth token.
    """
    user = request.user
    company = user.hr_profile.company if hasattr(user, 'hr_profile') else None

    # Log logout activity
    if company:
        ActivityLog.objects.create(
            user=user,
            company=company,
            activity_type='LOGOUT',
            details_json={'username': user.username, 'company_id': company.id}
        )
    request.user.auth_token.delete() # Delete the token
    logout(request) # Logout from session
    return Response({'message': 'Successfully logged out.'}, status=status.HTTP_200_OK)

# --- Candidate Management Views ---

class CandidateListCreateView(APIView):
    """
    List all candidates for the authenticated HR's company, or create a new candidate.
    This can serve as the main dashboard view for candidates.
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, IsCompanyUser]

    def get(self, request):
        """
        List all candidates for the authenticated HR's company.
        """
        candidates = Candidate.objects.filter(created_by=request.user)
        serializer = CandidateSerializer(candidates, many=True)
        return Response(serializer.data)

    def post(self, request):
        """
        Create a new candidate for the authenticated HR's company.
        """
        data = request.data.copy()
        data['created_by'] = request.user.id
        serializer = CandidateSerializer(data=data)
        if serializer.is_valid():
            candidate = serializer.save()
            ActivityLog.objects.create(
                user=request.user,
                company=request.user.hr_profile.company,
                activity_type='CANDIDATE_CREATE',
                details_json={
                    'candidate_id': candidate.id,
                    'candidate_name': candidate.name,
                    'candidate_email': candidate.email
                }
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsCompanyUser])
def candidate_detail_update_status(request, pk):
    """
    Retrieve or update a specific candidate's details and status.
    This is where 'Select', 'Review', 'Reject' actions will trigger PUT requests.
    """
    hr_company = request.user.hr_profile.company
    try:
        # Ensure candidate belongs to the HR's company
        candidate = Candidate.objects.get(pk=pk, company=hr_company)
    except Candidate.DoesNotExist:
        return Response({'error': 'Candidate not found or not accessible by your company.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = CandidateSerializer(candidate)
        return Response(serializer.data)

    elif request.method == 'PUT':
        old_status = candidate.status
        serializer = CandidateSerializer(candidate, data=request.data, partial=True) # partial=True for status update only
        if serializer.is_valid():
            candidate = serializer.save()

            # If status changed, log it in CandidateStatusLog
            if old_status != candidate.status:
                CandidateStatusLog.objects.create(
                    candidate=candidate,
                    user=request.user,
                    old_status=old_status,
                    new_status=candidate.status,
                    notes=request.data.get('status_notes', '') # Optional notes from HR
                )
                # Also update last_status_update on Candidate model
                candidate.last_status_update = timezone.now()
                candidate.save(update_fields=['last_status_update'])

                # Log general activity as well
                ActivityLog.objects.create(
                    user=request.user,
                    company=hr_company,
                    activity_type='CANDIDATE_STATUS_UPDATE',
                    details_json={
                        'candidate_id': candidate.id,
                        'name': candidate.name,
                        'old_status': old_status,
                        'new_status': candidate.status
                    }
                )

            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# --- Sourcing & Analysis Endpoints ---

@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsCompanyUser])
def upload_resume_api(request):
    """
    Uploads a resume file, parses it using resume_parse.py, creates/updates a Candidate, and logs activity.
    """
    user = request.user
    hr_company = user.hr_profile.company

    if 'resume_file' not in request.FILES:
        return Response({'error': 'No resume file provided'}, status=status.HTTP_400_BAD_REQUEST)

    resume_file = request.FILES['resume_file']

    try:
        # 1. Save the file
        company_media_path = os.path.join('media', 'resumes', str(hr_company.id))
        os.makedirs(company_media_path, exist_ok=True)
        file_path = os.path.join(company_media_path, resume_file.name)
        with open(file_path, 'wb+') as destination:
            for chunk in resume_file.chunks():
                destination.write(chunk)

        # 2. Extract text content from the file
        # You'll need to implement text extraction based on file type (PDF, DOCX, etc.)
        # For now, assuming text content is available
        resume_text = resume_file.read().decode('utf-8')

        # 3. Parse resume details using resume_parse.py
        from .resume_parse import extract_resume_details
        extracted_data = extract_resume_details(resume_text)
        if not extracted_data or not extracted_data.personal_info.email:
            ActivityLog.objects.create(
                user=user,
                company=hr_company,
                activity_type='RESUME_UPLOAD_ERROR',
                details_json={'filename': resume_file.name, 'error': 'Failed to extract personal info or email.'}
            )
            return Response({'error': 'Failed to extract essential data (like email) from resume. Please check format.'}, 
                          status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 4. Create/Update Candidate record
        candidate, created = Candidate.objects.update_or_create(
            company=hr_company,
            email=extracted_data.personal_info.email,
            defaults={
                'name': extracted_data.personal_info.name,
                'phone': extracted_data.personal_info.phone or '',
                'linkedin_url': extracted_data.personal_info.linkedin_url,
                'resume_file_path': file_path,
                'status': 'NEW',
                'last_status_update': timezone.now()
            }
        )

        # 5. Update Experience records
        candidate.experiences.all().delete()
        for exp in extracted_data.professional_experience or []:
            start_date = parser.parse(exp.start_date).date() if exp.start_date else None
            end_date = parser.parse(exp.end_date).date() if exp.end_date else None
            Experience.objects.create(
                candidate=candidate,
                role=exp.role or '',
                company=exp.company or '',
                start_date=start_date,
                end_date=end_date,
                description='\n'.join(exp.responsibilities) if exp.responsibilities else ''
            )

        # 6. Update Skills
        candidate.candidateskill_set.all().delete()
        if extracted_data.technical_skills:
            all_skills = []
            if extracted_data.technical_skills.technical_skills:
                all_skills.extend(extracted_data.technical_skills.technical_skills)
            if extracted_data.technical_skills.frameworks_libraries:
                all_skills.extend(extracted_data.technical_skills.frameworks_libraries)
            if extracted_data.technical_skills.tools:
                all_skills.extend(extracted_data.technical_skills.tools)
            
            for skill_name in all_skills:
                skill_obj, _ = Skill.objects.get_or_create(skill_name=skill_name.strip())
                CandidateSkill.objects.get_or_create(candidate=candidate, skill=skill_obj)

        # 7. Update Projects
        candidate.projects.all().delete()
        for proj in extracted_data.projects or []:
            Project.objects.create(
                candidate=candidate,
                name=proj.project_name or '',
                description=proj.description or ''
            )

        # Log activity
        ActivityLog.objects.create(
            user=user,
            company=hr_company,
            activity_type='RESUME_UPLOAD',
            details_json={
                'candidate_id': candidate.id,
                'resume_filename': resume_file.name,
                'is_new_candidate': created,
                'extracted_info': {
                    'name': extracted_data.personal_info.name,
                    'email': extracted_data.personal_info.email,
                    'experience_count': len(extracted_data.professional_experience or []),
                    'skills_count': len(all_skills) if 'all_skills' in locals() else 0,
                    'projects_count': len(extracted_data.projects or [])
                }
            }
        )

        return Response(
            {
                'message': 'Resume uploaded and processed successfully',
                'candidate_id': candidate.id,
                'extracted_data': extracted_data.dict()
            },
            status=status.HTTP_200_OK
        )

    except IntegrityError:
        return Response({'error': 'A candidate with this email already exists for your company.'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        ActivityLog.objects.create(
            user=user,
            company=hr_company,
            activity_type='RESUME_UPLOAD_ERROR',
            details_json={'filename': resume_file.name, 'error_message': str(e)}
        )
        return Response({'error': f'An unexpected error occurred: {str(e)}'}, 
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsCompanyUser])
def linkedin_search_api(request):
    """
    Performs a LinkedIn candidate search using JD_scrape.py functionality.
    Required fields:
    - query: The search query or job description to search for
    """
    user = request.user
    hr_company = user.hr_profile.company

    try:
        # Get query from request data
        query = request.data.get('query')
        if not query:
            return Response(
                {'error': 'Search query is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use JD_scrape.py functionality
        from .JD_scrape import search_and_store_profiles
        search_results = search_and_store_profiles(query, company=hr_company)

        # Log search activity
        ActivityLog.objects.create(
            user=user,
            company=hr_company,
            activity_type='LINKEDIN_SEARCH',
            details_json={
                'search_query': query,
                'results_count': len(search_results.get('organic', [])) if isinstance(search_results, dict) else 0
            }
        )

        # Return the search results
        return Response(search_results, status=status.HTTP_200_OK)

    except Exception as e:
        # Log the error with more details
        error_details = {
            'error_message': str(e),
            'error_type': type(e).__name__,
            'search_query': query if 'query' in locals() else None,
            'search_results_type': type(search_results).__name__ if 'search_results' in locals() else None
        }
        print("Error details:", error_details)
        
        ActivityLog.objects.create(
            user=user,
            company=hr_company,
            activity_type='LINKEDIN_SEARCH_ERROR',
            details_json=error_details
        )
        return Response(
            {'error': f'An unexpected error occurred: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsCompanyUser])
def scrape_and_analyze_linkedin_profile_api(request):
    """
    Scrapes a detailed LinkedIn profile using ScrapingDog API.
    Creates/updates Candidate record.
    """
    user = request.user
    hr_company = user.hr_profile.company

    try:
        data = json.loads(request.body.decode('utf-8'))
        linkedin_url = data.get('linkedin_url', '')

        if not linkedin_url:
            return Response({'error': 'LinkedIn URL is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Extract LinkedIn ID from URL
        linkedin_id = linkedin_url.split('/in/')[-1].strip('/').split('?')[0]

        # Call ScrapingDog API
        scrapingdog_api_key = os.getenv("SCRAPINGDOG_API_KEY")
        if not scrapingdog_api_key:
            return Response({'error': 'ScrapingDog API Key not configured'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        url = "https://api.scrapingdog.com/linkedin"
        params = {
            "api_key": scrapingdog_api_key,
            "type": "profile",
            "linkId": linkedin_id,
            "private": "true"
        }

        response = requests.get(url, params=params)
        print(response)
        if response.status_code != 200:
            return Response({'error': f'ScrapingDog API request failed with status code: {response.status_code}'}, 
                          status=status.HTTP_503_SERVICE_UNAVAILABLE)

        scraped_data = response.json()
        if not scraped_data or not isinstance(scraped_data, list) or len(scraped_data) == 0:
            return Response({'error': 'No valid data returned from ScrapingDog API'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Get the first profile from the list
        profile_data = scraped_data[0]

        # Remove unwanted fields
        if 'activities' in profile_data:
            del profile_data['activities']
        if 'people_also_viewed' in profile_data:
            del profile_data['people_also_viewed']
        if 'similar_profiles' in profile_data:
            del profile_data['similar_profiles']

        # Try to find existing candidate by LinkedIn URL first
        try:
            candidate = Candidate.objects.get(company=hr_company, linkedin_url=linkedin_url)
            is_new = False
        except Candidate.DoesNotExist:
            # If not found by LinkedIn URL, try to find by name
            try:
                candidate = Candidate.objects.get(company=hr_company, name=profile_data.get('fullName', 'N/A'))
                is_new = False
            except Candidate.DoesNotExist:
                # Create new candidate if not found
                candidate = Candidate.objects.create(
                    company=hr_company,
                    name=profile_data.get('fullName', 'N/A'),
                    phone='',
                    linkedin_url=linkedin_url,
                    status='NEW',
                    last_status_update=timezone.now(),
                    created_by=user  # Add the created_by field
                )
                is_new = True

        # Update candidate details
        candidate.name = profile_data.get('fullName', candidate.name)
        candidate.linkedin_url = linkedin_url
        if not candidate.phone:  # Only update phone if it's empty
            candidate.phone = ''
        if candidate.status == 'NEW':  # Only update status if it's NEW
            candidate.status = 'NEW'
            candidate.last_status_update = timezone.now()
        candidate.save()

        # Update related Experience
        candidate.experiences.all().delete()  # Clear existing experiences
        for exp in profile_data.get('experience', []):
            # Parse dates
            start_date = None
            end_date = None
            if exp.get('starts_at'):
                try:
                    start_date = parser.parse(exp['starts_at']).date()
                except:
                    pass
            if exp.get('ends_at') and exp['ends_at'] != 'Present':
                try:
                    end_date = parser.parse(exp['ends_at']).date()
                except:
                    pass

            Experience.objects.create(
                candidate=candidate,
                role=exp.get('position', ''),
                company=exp.get('company_name', ''),
                start_date=start_date,
                end_date=end_date,
                description=exp.get('summary', '')
            )

        # Log profile scrape activity
        ActivityLog.objects.create(
            user=user,
            company=hr_company,
            activity_type='PROFILE_SCRAPE',
            details_json={
                'linkedin_url': linkedin_url,
                'candidate_name': candidate.name,
                'candidate_id': candidate.id,
                'is_new_candidate': is_new,
                'scraped_data': {
                    'headline': profile_data.get('headline'),
                    'location': profile_data.get('location'),
                    'experience_count': len(profile_data.get('experience', [])),
                    'education_count': len(profile_data.get('education', []))
                }
            }
        )

        return Response(
            {
                'message': 'LinkedIn profile scraped and processed successfully',
                'candidate_id': candidate.id,
                'is_new_candidate': is_new,
                'scraped_data': profile_data
            },
            status=status.HTTP_200_OK
        )

    except requests.exceptions.RequestException as e:
        ActivityLog.objects.create(
            user=user,
            company=hr_company,
            activity_type='PROFILE_SCRAPE_ERROR',
            details_json={'error_message': f'ScrapingDog API error: {str(e)}', 'linkedin_url': linkedin_url}
        )
        return Response({'error': f'Failed to connect to ScrapingDog API: {str(e)}'}, 
                       status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as e:
        ActivityLog.objects.create(
            user=user,
            company=hr_company,
            activity_type='PROFILE_SCRAPE_ERROR',
            details_json={'error_message': str(e), 'linkedin_url': linkedin_url}
        )
        return Response({'error': f'An unexpected error occurred: {str(e)}'}, 
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- Dashboard / Reporting Views ---
@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsCompanyUser])
def hr_dashboard_summary(request):
    """
    Provides a summary of candidates and activities for the authenticated HR's company.
    This would be the main dashboard view upon login.
    """
    user = request.user
    hr_company = user.hr_profile.company

    # 1. Candidate Counts by Status
    candidate_status_counts = {}
    for choice_val, choice_display in Candidate.STATUS_CHOICES:
        candidate_status_counts[choice_val] = Candidate.objects.filter(
            company=hr_company,
            status=choice_val
        ).count()

    # 2. Recent Activities
    recent_activities = ActivityLog.objects.filter(company=hr_company).order_by('-timestamp')[:10] # Last 10 activities
    activity_data = []
    for activity in recent_activities:
        activity_data.append({
            'type': activity.activity_type,
            'timestamp': activity.timestamp,
            'details': activity.details_json,
            'user': activity.user.username
        })

    # 3. Recently Added/Modified Candidates (if desired, can reuse CandidateSerializer)
    recently_modified_candidates = Candidate.objects.filter(company=hr_company).order_by('-updated_at')[:5]
    recent_candidates_data = CandidateSerializer(recently_modified_candidates, many=True).data

    return Response({
        'company_id': hr_company.id,
        'company_name': hr_company.name,
        'candidate_status_counts': candidate_status_counts,
        'recent_activities': activity_data,
        'recently_modified_candidates': recent_candidates_data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsCompanyUser])
def generate_candidate_analysis(request):
    """
    Generates or retrieves an AI analysis comparing a candidate against a job description.
    
    Required fields in request body:
    - candidate_id: ID of the candidate to analyze
    - job_description: The job description text to compare against
    
    Returns:
    - AI analysis summary including match score and detailed breakdown
    """
    try:
        candidate_id = request.data.get('candidate_id')
        job_description = request.data.get('job_description')
        if not candidate_id or not job_description:
            return Response(
                {'error': 'Both candidate_id and job_description are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            candidate = Candidate.objects.get(
                id=candidate_id,
                created_by=request.user
            )
        except Candidate.DoesNotExist:
            return Response(
                {'error': 'Candidate not found or not accessible'},
                status=status.HTTP_404_NOT_FOUND
            )
        analysis = get_candidate_analysis(candidate, job_description)
        print(analysis)
        if not analysis:
            return Response(
                {'error': 'Failed to generate analysis'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        ActivityLog.objects.create(
            user=request.user,
            company=request.user.hr_profile.company,
            activity_type='AI_ANALYSIS_GENERATED',
            details_json={
                'candidate_id': candidate.id,
                'candidate_name': candidate.name,
                'analysis_id': analysis.id,
                'score': analysis.score
            }
        )
        return Response({
            'analysis_id': analysis.id,
            'candidate_name': candidate.name,
            'summary': analysis.summary_text,
            'score': analysis.score,
            'details': analysis.details_json,
            'created_at': analysis.created_at
        }, status=status.HTTP_200_OK)
    except Exception as e:
        ActivityLog.objects.create(
            user=request.user,
            company=request.user.hr_profile.company,
            activity_type='AI_ANALYSIS_ERROR',
            details_json={
                'error': str(e),
                'candidate_id': candidate_id if 'candidate_id' in locals() else None
            }
        )
        return Response(
            {'error': f'An unexpected error occurred: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

