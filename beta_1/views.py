from django.shortcuts import render
from rest_framework import viewsets
from .models import Candidate, Experience, Skill, CandidateSkill, Project, AISummary, LinkedInProfile
from .serializers import CandidateSerializer, ExperienceSerializer, SkillSerializer, CandidateSkillSerializer, ProjectSerializer, AISummarySerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.conf import settings
import os
import beta_1.resume_parse as resume_parse
import mimetypes
import pdfplumber
import docx
from dateutil import parser
import datetime
from beta_1 import JD_parse
from beta_1.JD_parse import calculate_total_experience
from beta_1.JD_scrape import search_and_store_profiles
import http.client
import json
from google import genai
from dotenv import load_dotenv
import re

load_dotenv()

def my_view(request):
    return render(request, "index.html")


def parse_date_string(date_str):
    try:
        # Try to parse full date, or fallback to first of month/year
        return parser.parse(date_str, default=datetime.datetime(1900, 1, 1)).date()
    except Exception:
        return None

# Placeholder for resume parsing logic
def parse_resume(file_path):
    # This should be replaced with actual resume parsing logic
    # For now, return dummy data
    return {
        'name': 'John Doe',
        'email': 'john@example.com',
        'phone': '1234567890',
        'linkedin_url': '',
        'github_url': '',
        'skills': ['Python', 'Django'],
        'experiences': [
            {'role': 'Software Engineer', 'company': 'ABC Corp', 'start_date': '2020-01-01', 'end_date': '2022-01-01', 'description': 'Worked on backend.'}
        ],
        'projects': [
            {'project_name': 'Resume Parser', 'description': 'Built a resume parser.'}
        ]
    }

# Placeholder for AI summary generation
def generate_ai_summary(candidate, job_description):
    return f"Summary for {candidate.name} relevant to the job description."

def extract_text_from_resume(file_path):
    mime, _ = mimetypes.guess_type(file_path)
    if mime == 'application/pdf':
        with pdfplumber.open(file_path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    elif mime in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']:
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    else:  # Assume plain text
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

class ResumeUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file_obj = request.FILES.get('resume')
        if not file_obj:
            return Response({'error': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)
        # Save file
        resume_dir = os.path.join(settings.BASE_DIR, 'resumes')
        os.makedirs(resume_dir, exist_ok=True)
        file_path = os.path.join(resume_dir, file_obj.name)
        with open(file_path, 'wb+') as destination:
            for chunk in file_obj.chunks():
                destination.write(chunk)
        # Read file content for parsing
        resume_content = extract_text_from_resume(file_path)
        parsed = resume_parse.extract_resume_details(resume_content)
        if not parsed or not parsed.personal_info:
            return Response({'error': 'Failed to parse resume.'}, status=400)
        info = parsed.personal_info
        # Check if candidate exists by email
        candidate, created = Candidate.objects.get_or_create(
            email=info.email or '',
            defaults={
                'name': info.name or '',
                'phone': info.phone or '',
                'linkedin_url': info.linkedin_url or '',
                'github_url': '',  # Not parsed in current schema
                'resume_file_path': file_path
            }
        )
        if not created:
            # Update existing candidate fields
            candidate.name = info.name or candidate.name
            candidate.phone = info.phone or candidate.phone
            candidate.linkedin_url = info.linkedin_url or candidate.linkedin_url
            candidate.github_url = candidate.github_url  # Not parsed
            candidate.resume_file_path = file_path
            candidate.save()
            # Remove old related data
            CandidateSkill.objects.filter(candidate=candidate).delete()
            Experience.objects.filter(candidate=candidate).delete()
            Project.objects.filter(candidate=candidate).delete()
        # Add skills
        skills = []
        if parsed.technical_skills:
            if parsed.technical_skills.technical_skills:
                skills += parsed.technical_skills.technical_skills
            if parsed.technical_skills.frameworks_libraries:
                skills += parsed.technical_skills.frameworks_libraries
            if parsed.technical_skills.tools:
                skills += parsed.technical_skills.tools
        for skill_name in set(skills):
            skill, _ = Skill.objects.get_or_create(skill_name=skill_name)
            CandidateSkill.objects.create(candidate=candidate, skill=skill)
        # Add experiences
        if parsed.professional_experience:
            for exp in parsed.professional_experience:
                Experience.objects.create(
                    candidate=candidate,
                    role=exp.role or '',
                    company=exp.company or '',
                    start_date=parse_date_string(exp.start_date) if exp.start_date else None,
                    end_date=parse_date_string(exp.end_date) if exp.end_date else None,
                    description='; '.join(exp.responsibilities) if exp.responsibilities else ''
                )
        # Add projects
        if parsed.projects:
            for proj in parsed.projects:
                Project.objects.create(
                    candidate=candidate,
                    project_name=proj.project_name or '',
                    description=proj.description or ''
                )
        # Add education, etc. as needed
        return Response({'success': True, 'candidate_id': candidate.id})

class CandidateDetailView(APIView):
    def get(self, request, candidate_id):
        candidate = get_object_or_404(Candidate, id=candidate_id)
        serializer = CandidateSerializer(candidate)
        # Add related info
        data = serializer.data
        data['skills'] = [cs.skill.skill_name for cs in CandidateSkill.objects.filter(candidate=candidate)]
        data['experiences'] = ExperienceSerializer(Experience.objects.filter(candidate=candidate), many=True).data
        data['projects'] = ProjectSerializer(Project.objects.filter(candidate=candidate), many=True).data
        summaries = AISummary.objects.filter(candidate=candidate)
        data['summaries'] = [
            {'job_description_hash': s.job_description_hash, 'summary_text': s.summary_text}
            for s in summaries
        ]
        return Response(data)

class CandidateResumeView(APIView):
    def get(self, request, candidate_id):
        candidate = get_object_or_404(Candidate, id=candidate_id)
        if not candidate.resume_file_path or not os.path.exists(candidate.resume_file_path):
            raise Http404
        return FileResponse(open(candidate.resume_file_path, 'rb'), as_attachment=True)

class CandidateSearchView(APIView):
    def post(self, request):
        jd_text = request.data.get('query', '')
        matches = JD_parse.get_candidate_scores_from_llm(jd_text)
        print(matches)
        if not matches:
            return Response({'error': 'No matches found.'}, status=404)
        # Serialize candidates and their match details
        results = []
        candidate_summaries = matches.get('candidate_summaries', {})
        for candidate in matches['ranked_candidates']:
            # Fetch the candidate object from DB
            candidate_obj = Candidate.objects.get(id=candidate['candidate_id'])
            # Get all roles from experiences
            roles = [exp.role for exp in candidate_obj.experiences.all()]
            # Calculate total experience years
            total_experience_years = calculate_total_experience(candidate_obj)
            results.append({
                'candidate_id': candidate['candidate_id'],
                'name': candidate['name'],
                'email': candidate['email'],
                'total_score': candidate['total_score'],
                'skill_score': candidate.get('skill_score'),
                'project_score': candidate.get('project_score'),
                'roles': roles,
                'total_experience_years': round(total_experience_years, 2),
            })
            # Save candidate summary in background (not shown in response)
            summary_text = candidate_summaries.get(str(candidate['candidate_id']))
            if summary_text:
                AISummary.objects.update_or_create(
                    candidate=candidate_obj,
                    job_description_hash=str(hash(jd_text)),
                    defaults={'summary_text': summary_text}
                )
        return Response({'results': results})

class CandidateSummaryView(APIView):
    def post(self, request, candidate_id):
        job_description = request.data.get('job_description', '')
        job_description_hash = request.data.get('job_description_hash', '')
        candidate = get_object_or_404(Candidate, id=candidate_id)
        summary_text = generate_ai_summary(candidate, job_description)
        summary, _ = AISummary.objects.get_or_create(
            candidate=candidate,
            job_description_hash=job_description_hash,
            defaults={'summary_text': summary_text}
        )
        return Response({'summary_text': summary.summary_text})

    def get(self, request, candidate_id):
        jd_hash = request.query_params.get('jd_hash')
        candidate = get_object_or_404(Candidate, id=candidate_id)
        try:
            summary = AISummary.objects.get(candidate=candidate, job_description_hash=jd_hash)
            return Response({'summary_text': summary.summary_text})
        except AISummary.DoesNotExist:
            return Response({'error': 'Summary not found.'}, status=404)

class JDScraperView(APIView):
    def post(self, request):
        # Get the job description or search query from the request
        jd_content = request.data.get('query', '')
        
        # Use the search_and_store_profiles function to search and store results
        result = search_and_store_profiles(jd_content)
        
        if 'error' in result:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        return Response(result)


