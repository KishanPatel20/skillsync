from google import genai
from pydantic import BaseModel, Field, RootModel
from typing import List, Optional, Dict, Any
import os # For API Key
from dotenv import load_dotenv
from django.utils import timezone
from .models import AISummary, Candidate, Company
import hashlib

load_dotenv()

# --- Pydantic Models for Structured Response ---
# These models define the expected JSON output structure that the LLM should follow.
# This structure is also described in the prompt to guide the LLM.
api_key = os.getenv("GEMINI_API")
print(api_key)

class SkillMatch(BaseModel):
    skill_name: str = None
    jd_requirement_description: str = None
    candidate_evidence_and_assessment: Optional[str] = None
    match_level: str = None
    commentary: Optional[str] = None

class ExperienceMatch(BaseModel):
    job_title_in_resume: Optional[str] = None
    company_and_duration: Optional[str] = None
    relevance_to_jd: str = None
    key_achievements_or_responsibilities_matched: List[str] = None
    experience_notes: Optional[str] = None

class EducationAndCertificationMatch(BaseModel):
    education_match_summary: Optional[str] = None
    certification_match_summary: Optional[str] = None

class CandidateAnalysisResponse(BaseModel):
    candidate_name: Optional[str] = None
    job_title_from_jd: str = None
    overall_suitability_score: float = None
    summary_assessment: str = None
    strengths_aligned_with_jd: List[str] = None
    areas_for_further_exploration_or_concern: List[str] = None
    detailed_skill_match_analysis: List[SkillMatch] = None
    relevant_experience_summary: List[ExperienceMatch] = None
    education_and_certification_match: EducationAndCertificationMatch
    suggested_interview_questions: List[str] = None
    potential_red_flags: List[str] = None



def generate_ai_summary(jd_content: str, resume_content: str, candidate: Candidate, company: Company) -> AISummary:
    """
    Generates an AI summary comparing a candidate's resume against a job description
    and stores it in the database.
    
    Args:
        jd_content: The job description text
        resume_content: The candidate's resume or profile text
        candidate: The Candidate model instance
        company: The Company model instance
        
    Returns:
        AISummary model instance containing the analysis
    """
    # Generate a hash of the job description for caching
    jd_hash = hashlib.md5(jd_content.encode()).hexdigest()
    
    # Check if we already have an analysis for this candidate and JD
    existing_summary = AISummary.objects.filter(
        candidate=candidate,
        job_description_hash=jd_hash
    ).first()
    print("Existing Summary ",existing_summary)
    if existing_summary:
        return existing_summary
    
    # Generate new analysis
    analysis = extract_jd_requirements(jd_content, resume_content)
    if not analysis:
        raise ValueError("Failed to generate analysis")
    
    # Create and save the AI summary
    summary = AISummary.objects.create(
        candidate=candidate,
        company=company,
        created_by=candidate.created_by,
        job_description_hash=jd_hash,
        summary_text=analysis.summary_assessment,
        score=analysis.overall_suitability_score,
        details_json=analysis.dict(),
        created_at=timezone.now()
    )
    
    return summary

def get_candidate_analysis(candidate: Candidate, jd_content: str) -> Optional[AISummary]:
    """
    Retrieves or generates an AI analysis for a candidate against a job description.
    If no resume file is available, gathers candidate details from the database (skills, experience, etc.).
    Wraps the entire logic in a try-except block to handle errors gracefully.
    Skips gathering skills, experiences, and education if they are not present on the candidate object.
    
    Args:
        candidate: The Candidate model instance
        jd_content: The job description text
        
    Returns:
        AISummary model instance if successful, None otherwise
    """
    try:
        # Generate hash of the job description
        jd_hash = hashlib.md5(jd_content.encode()).hexdigest()
        
        # Try to get existing analysis
        summary = AISummary.objects.filter(
            candidate=candidate,
            job_description_hash=jd_hash
        ).first()
        
        if summary:
            return summary
            
        # If no existing analysis, gather candidate details from the database
        resume_content = ""
        try:
            if candidate.resume_file_path:
                with open(candidate.resume_file_path, 'r', encoding='utf-8') as f:
                    resume_content = f.read()
        except Exception as e:
            print(f"Error reading resume file: {str(e)}")
            resume_content = ""
        
        # If resume content is empty, gather details from the database
        if not resume_content:
            try:
                resume_content = f"Name: {candidate.name}\n"
                resume_content += f"Email: {candidate.email}\n"
                resume_content += f"Phone: {candidate.phone}\n"
                resume_content += f"LinkedIn: {candidate.linkedin_url}\n"
                resume_content += f"GitHub: {candidate.github_url}\n\n"
                
                # Gather skills if present
                if hasattr(candidate, 'skills'):
                    skills = candidate.skills.all()
                    resume_content += "Skills:\n"
                    for skill in skills:
                        resume_content += f"- {skill.name}\n"
                
                # Gather experiences if present
                if hasattr(candidate, 'experiences'):
                    experiences = candidate.experiences.all()
                    resume_content += "\nExperience:\n"
                    for exp in experiences:
                        # Use position instead of title if that's the field name
                        position = getattr(exp, 'position', getattr(exp, 'title', 'N/A'))
                        company = getattr(exp, 'company', 'N/A')
                        start_date = getattr(exp, 'start_date', 'N/A')
                        end_date = getattr(exp, 'end_date', 'N/A')
                        description = getattr(exp, 'description', 'N/A')
                        
                        resume_content += f"- {position} at {company} ({start_date} - {end_date})\n"
                        resume_content += f"  {description}\n"
                
                # Gather education if present
                if hasattr(candidate, 'education'):
                    education = candidate.education.all()
                    resume_content += "\nEducation:\n"
                    for edu in education:
                        degree = getattr(edu, 'degree', 'N/A')
                        field = getattr(edu, 'field', 'N/A')
                        institution = getattr(edu, 'institution', 'N/A')
                        start_date = getattr(edu, 'start_date', 'N/A')
                        end_date = getattr(edu, 'end_date', 'N/A')
                        
                        resume_content += f"- {degree} in {field} from {institution} ({start_date} - {end_date})\n"
            except Exception as e:
                print(f"Error gathering candidate details from database: {str(e)}")
                resume_content = ""
        print(f"Resume content for {candidate.name}: {resume_content}")
        # Generate new analysis
        return generate_ai_summary(
            jd_content=jd_content,
            resume_content=resume_content,
            candidate=candidate,
            company=candidate.company
        )
        
    except Exception as e:
        print(f"Error in get_candidate_analysis: {str(e)}")
        return None

def extract_jd_requirements(jd_content: str, resume_content: str):
    client = genai.Client(api_key=api_key)
    print("api" , api_key)
    prompt = f"""
    ou are an expert AI Talent Acquisition Assistant specializing in the IT industry. Your primary function is to conduct a comprehensive and unbiased analysis of a candidate's profile or resume against a specific Job Description (JD).

**Objective:** Evaluate the candidate's suitability for the role and generate a structured JSON output detailing your findings. This will enable HR personnel to make informed decisions quickly.

**Inputs:**
1.  `[JOB_DESCRIPTION_HERE]`: {jd_content}
2.  `[CANDIDATE_PROFILE_HERE]`: {resume_content}

**Core Analysis Instructions:**
1.  **Deep Understanding:** Meticulously parse both the JD and the Candidate Profile. Identify core requirements, essential skills (technical and soft), experience levels, educational prerequisites, and any specific keywords or technologies mentioned in the JD.
2.  **Comparative Evaluation:**
    * **Skills Match:** Systematically compare skills listed in the JD with those demonstrated in the candidate's profile. Note any direct matches, transferable skills, or apparent gaps.
    * **Experience Relevance:** Assess the candidate's work history, focusing on the relevance of previous roles, responsibilities, duration, and accomplishments to the target role's requirements.
    * **Qualifications Alignment:** Verify if the candidate's educational background, certifications, and other qualifications meet those specified in the JD.
3.  **Insight Generation:** Based on your comparative analysis, synthesize the information to identify:
    * The candidate's principal strengths that align with the JD.
    * Areas where the candidate's profile indicates potential weaknesses, gaps, or misalignments with the JD.
    * An overall suitability score.
    * Potential red flags (e.g., unexplained career gaps, lack of critical skills, insufficient experience for key responsibilities).
    * Targeted interview questions to clarify ambiguities or delve deeper into critical areas.

**Mandatory Output Format:**
Your entire response MUST be a single, valid JSON object. Do NOT include any introductory or concluding remarks, explanations, or text outside of this JSON object. Adhere strictly to the structure outlined below.

**JSON Output Structure Definition:**
```json
{{
  "candidate_name": "{{candidate_name}}",
  "job_title_from_jd": "{{job_title_from_jd}}",
  "overall_suitability_score": "{{overall_suitability_score}}",
  "summary_assessment": "{{summary_assessment}}",
  "strengths_aligned_with_jd": [
    "{{strength1}}",
    "{{strength2}}"
  ],
  "areas_for_further_exploration_or_concern": [
    "{{concern1}}",
    "{{concern2}}"
  ],
  "detailed_skill_match_analysis": [
    {{
      "skill_name": "{{skill_name1}}",
      "jd_requirement_description": "{{jd_requirement_description1}}",
      "candidate_evidence_and_assessment": "{{candidate_evidence_and_assessment1}}",
      "match_level": "{{match_level1}}",
      "commentary": "{{commentary1}}"
    }},
    {{
      "skill_name": "{{skill_name2}}",
      "jd_requirement_description": "{{jd_requirement_description2}}",
      "candidate_evidence_and_assessment": "{{candidate_evidence_and_assessment2}}",
      "match_level": "{{match_level2}}",
      "commentary": "{{commentary2}}"
    }}
  ],
  "relevant_experience_summary": [
    {{
      "job_title_in_resume": "{{job_title_in_resume1}}",
      "company_and_duration": "{{company_and_duration1}}",
      "relevance_to_jd": "{{relevance_to_jd1}}",
      "key_achievements_or_responsibilities_matched": [
        "{{achievement_or_responsibility1_1}}",
        "{{achievement_or_responsibility1_2}}"
      ],
      "experience_notes": "{{experience_notes1}}"
    }},
    {{
      "job_title_in_resume": "{{job_title_in_resume2}}",
      "company_and_duration": "{{company_and_duration2}}",
      "relevance_to_jd": "{{relevance_to_jd2}}",
      "key_achievements_or_responsibilities_matched": [
        "{{achievement_or_responsibility2_1}}",
        "{{achievement_or_responsibility2_2}}"
      ],
      "experience_notes": "{{experience_notes2}}"
    }}
  ],
  "education_and_certification_match": {{
    "education_match_summary": "{{education_match_summary}}",
    "certification_match_summary": "{{certification_match_summary}}"
  }},
  "suggested_interview_questions": [
    "{{question1}}",
    "{{question2}}"
  ],
  "potential_red_flags": [
    "{{red_flag1}}",
    "{{red_flag2}}"
  ]
}}
    """
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": CandidateAnalysisResponse,
            },
        )
        print(response)
        # print(resume_content)
        return response.parsed
    except Exception as e:
        print(f"Error during resume extraction: {e}")
        print(f"Raw response: {response.text if 'response' in locals() else 'No response'}")
        return None
