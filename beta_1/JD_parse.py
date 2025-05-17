from django.db.models import Q
from dateutil import parser
import datetime
import re
from .models import Candidate, Skill, Experience, Project  # Import your models
from google import genai
from pydantic import BaseModel
import json
from dotenv import load_dotenv
import os
from .serializers import CandidateSerializer , CandidateFullSerializer # Import at the top

load_dotenv()

api_key = os.getenv("GEMINI_API")

class JDRequirements(BaseModel):
    skills: list[str] | None = None
    experience_years: int | None = None
    role: str | None = None
    location: str | None = None
    keywords: list[str] | None = None
    education: str | None = None
    project_keywords: list[str] | None = None

class CandidateScore(BaseModel):
    candidate_id: int
    name: str
    email: str
    total_score: float
    skill_score: float
    experience_score: float
    role_score: float
    location_score: float
    keyword_score: float
    matched_skills: list[str]
    candidate_experience: str
    required_experience: str
    matched_roles: list[str]
    required_role: str
    candidate_location: str
    required_location: str
    matched_keywords: list[str]
    overfit: bool | None = None
    underfit: bool | None = None

def extract_jd_requirements(jd_content: str) -> JDRequirements | None:
    client = genai.Client(api_key=api_key)
    prompt = f"""
    Extract the key requirements from the following job description and format them as a JSON object according to the schema provided.

    Job Description:
    ```
    {jd_content}
    ```

    JSON Schema:
    ```json
    {{
      "skills": "list[string] | null",
      "experience_years": "integer | null",
      "role": "string | null",
      "location": "string | null",
      "keywords": "list[string] | null",
      "education": "string | null",
      "project_keywords": "list[string] | null"
    }}
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"response_mime_type": "application/json", "response_schema": JDRequirements},
        )
        return response.parsed
    except Exception as e:
        print(f"Error extracting JD requirements: {e}")
        return None

def find_matching_candidates(jd_content: str):
    jd_requirements = extract_jd_requirements(jd_content)
    if not jd_requirements:
        return []

    candidates = Candidate.objects.all()
    scored_candidates_with_details = []

    for candidate in candidates:
        score, details = score_candidate(candidate, jd_requirements)
        scored_candidates_with_details.append((candidate, score, details))

    ranked_candidates = sorted(scored_candidates_with_details, key=lambda item: item[1], reverse=True)
    return ranked_candidates

def score_candidate(candidate, jd_requirements):
    score = 0
    details = {}

    # Skills
    if jd_requirements.skills:
        candidate_skills_lower = set(cs.skill.skill_name.lower() for cs in candidate.candidateskill_set.all())
        matched = [s for s in jd_requirements.skills if s.lower() in candidate_skills_lower]
        skill_score = (len(matched) / len(jd_requirements.skills)) * 30 # Increased weight
        details['matched_skills'] = matched
    else:
        skill_score = 30
        details['matched_skills'] = []
    score += skill_score
    details['skill_score'] = skill_score

    # Experience
    candidate_exp = calculate_total_experience(candidate)
    if jd_requirements.experience_years is not None:
        exp_diff = candidate_exp - jd_requirements.experience_years
        if abs(exp_diff) <= 1:
            exp_score = 25 # Increased weight
        elif abs(exp_diff) <= 3:
            exp_score = 15
        else:
            exp_score = 5
        # Overfit/underfit penalty
        if exp_diff > 5:
            exp_score -= 5
            details['overfit'] = True
        elif exp_diff < -3:
            exp_score -= 5
            details['underfit'] = True
        details['candidate_experience'] = f"{candidate_exp:.2f} years"
        details['required_experience'] = f"{jd_requirements.experience_years} years"
    else:
        exp_score = 25
        details['candidate_experience'] = f"{candidate_exp:.2f} years"
        details['required_experience'] = "N/A"
    score += exp_score
    details['experience_score'] = exp_score

    # Role
    role_score = 0
    matched_roles = []
    if jd_requirements.role:
        for exp in candidate.experiences.all():
            if exp.role and jd_requirements.role.lower() in exp.role.lower():
                matched_roles.append(exp.role)
        if any(jd_requirements.role.lower() == r.lower() for r in matched_roles):
            role_score = 20 # Increased weight
        elif matched_roles:
            role_score = 10
    details['matched_roles'] = matched_roles
    details['role_score'] = role_score
    details['required_role'] = jd_requirements.role
    score += role_score

    # Location
    location_score = 0
    candidate_location = getattr(candidate, 'location', None) or getattr(candidate, 'linkedin_url', '')
    if jd_requirements.location:
        if candidate_location and jd_requirements.location.lower() == candidate_location.lower():
            location_score = 10
        elif candidate_location and jd_requirements.location.lower() in candidate_location.lower():
            location_score = 5
    details['candidate_location'] = candidate_location
    details['location_score'] = location_score
    details['required_location'] = jd_requirements.location
    score += location_score

    # Keywords
    keyword_score = 0
    matched_keywords = []
    if jd_requirements.keywords:
        candidate_text = ' '.join([
            ' '.join([cs.skill.skill_name for cs in candidate.candidateskill_set.all()]),
            ' '.join([exp.role or '' for exp in candidate.experiences.all()]),
            candidate_location or ''
        ]).lower()
        for kw in jd_requirements.keywords:
            if kw.lower() in candidate_text:
                matched_keywords.append(kw)
        keyword_score = (len(matched_keywords) / len(jd_requirements.keywords)) * 15 # Increased weight
    details['matched_keywords'] = matched_keywords
    details['keyword_score'] = keyword_score
    details['required_keywords'] = jd_requirements.keywords
    score += keyword_score

    details['total_score'] = score
    return score, details

def calculate_total_experience(candidate):
    total_experience_years = 0
    for exp in candidate.experiences.all():
        if exp.start_date:
            end_date = exp.end_date if exp.end_date else datetime.date.today()
            duration = end_date - exp.start_date
            total_experience_years += duration.days / 365.25
    return total_experience_years

def get_candidate_scores_from_llm(jd_content: str):
    ranked_candidates_with_details = find_matching_candidates(jd_content)
    client = genai.Client(api_key=api_key)
    candidate_scores_list = []

    for candidate, score, details in ranked_candidates_with_details:
        # Serialize full candidate info
        candidate_data = CandidateFullSerializer(candidate).data

        # Add scoring details
        # candidate_data.update({
        #     "total_score": score,
        #     "skill_score": details.get('skill_score', 0),
        #     "experience_score": details.get('experience_score', 0),
        #     "role_score": details.get('role_score', 0),
        #     "location_score": details.get('location_score', 0),
        #     "keyword_score": details.get('keyword_score', 0),
        #     "matched_skills": details.get('matched_skills', []),
        #     "candidate_experience": details.get('candidate_experience', 'N/A'),
        #     "required_experience": details.get('required_experience', 'N/A'),
        #     "matched_roles": details.get('matched_roles', []),
        #     "required_role": details.get('required_role', 'N/A'),
        #     "candidate_location": details.get('candidate_location', 'N/A'),
        #     "required_location": details.get('required_location', 'N/A'),
        #     "matched_keywords": details.get('matched_keywords', []),
        #     "overfit": details.get('overfit'),
        #     "underfit": details.get('underfit'),
        # })
        candidate_scores_list.append(candidate_data)

    
    prompt = f"""Based on the following Job Description:
{jd_content}

And the following list of candidate scores and matching details:

{json.dumps(candidate_scores_list, indent=2)}
Re-evaluate the provided scores.

Provide a concise JSON response that includes two top-level keys:

"ranked_candidates": A list of candidates. Each item in the list should represent a candidate and include their "candidate_id", "name", "email", "total_score", "skill_score", and "project_score". Rank the candidates by the re-evaluated "total_score" in descending order.

"candidate_summaries": A dictionary where each key is a "candidate_id" and the value is a short paragraph summarizing the strengths and weaknesses of that candidate based on the provided scores and matching details, highlighting aspects relevant to the job description.
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error getting candidate scores from LLM: {e}")
        return {"ranked_candidates": [{"error": "Failed to get LLM scores"}]}