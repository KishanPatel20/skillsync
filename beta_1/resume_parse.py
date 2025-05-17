from google import genai
from pydantic import BaseModel
import json
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("GEMINI_API")
class PersonalInfo(BaseModel):
    name: str | None = None
    title: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None

class Experience(BaseModel):
    company: str | None = None
    location: str | None = None
    role: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    responsibilities: list[str] | None = None

class Education(BaseModel):
    institution: str | None = None
    location: str | None = None
    degree: str | None = None
    start_date: str | None = None
    end_date: str | None = None

class TechnicalSkills(BaseModel):
    technical_skills: list[str] | None = None
    frameworks_libraries: list[str] | None = None
    tools: list[str] | None = None

class AdditionalInfo(BaseModel):
    info: list[str] | None = None

class Project(BaseModel):
    project_name: str | None = None
    description: str | None = None

class ResumeData(BaseModel):
    personal_info: PersonalInfo | None = None
    professional_experience: list[Experience] | None = None
    education: list[Education] | None = None
    technical_skills: TechnicalSkills | None = None
    additional_information: list[str] | None = None
    projects: list[Project] | None = None

def extract_resume_details(resume_content: str) -> ResumeData | None:
    """
    Extracts details from resume content using a Generative AI model.

    Args:
        resume_content: The text content of the resume.
        api_key: Your Google Cloud Gen AI API key.

    Returns:
        A ResumeData object containing the extracted information, or None if extraction fails.
    """
    client = genai.Client(api_key=api_key)
    prompt = f"""
    Extract the following information from the resume content provided below and format it as a JSON object according to the schema provided.

    Resume Content:
    ```
    {resume_content}
    ```

    JSON Schema:
    ```json
    {{
      "personal_info": {{
        "name": "string | null",
        "title": "string | null",
        "linkedin_url": "string | null",
        "email": "string | null",
        "phone": "string | null",
        "location": "string | null"
      }},
      "professional_experience": [
        {{
          "company": "string | null",
          "location": "string | null",
          "role": "string | null",
          "start_date": "string | null",
          "end_date": "string | null",
          "responsibilities": "list[string] | null"
        }}
      ],
      "education": [
        {{
          "institution": "string | null",
          "location": "string | null",
          "degree": "string | null",
          "start_date": "string | null",
          "end_date": "string | null"
        }}
      ],
      "technical_skills": {{
        "technical_skills": "list[string] | null",
        "frameworks_libraries": "list[string] | null",
        "tools": "list[string] | null"
      }},
      "additional_information": "list[string] | null",
      "projects": [
        {{
          "project_name": "string | null",
          "description": "string | null"
        }}
      ]
    }}
    ```
    Ensure Projects are extracted as a list of projects and full details are extracted for each project.
    Ensure that the JSON object is valid and all extracted information is placed in the correct fields. If a piece of information is not found, set the corresponding field to null. For lists, if no items are found, return an empty list.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": ResumeData,
            },
        )
        print(response.text)
        # print(resume_content)
        return response.parsed
    except Exception as e:
        print(f"Error during resume extraction: {e}")
        print(f"Raw response: {response.text if 'response' in locals() else 'No response'}")
        return None

