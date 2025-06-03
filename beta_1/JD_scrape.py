from google import genai
from dotenv import load_dotenv
import os
import http.client
import json
import re
from .models import LinkedInProfile, Company

load_dotenv()

api_key = os.getenv("GEMINI_API")

def extract_linkedin_id(url):
    # Extract LinkedIn ID from URL
    # Example URL: https://linkedin.com/in/johndoe
    match = re.search(r'linkedin\.com/in/([^/]+)', url)
    return match.group(1) if match else None

def extract_jd_requirements(jd_content: str):
    client = genai.Client(api_key=api_key)
    prompt = f"""
    # LinkedIn Profile Search Query Generator

## Role
You are an expert in creating precise Google search queries to identify relevant LinkedIn profiles for recruitment purposes.

## Objective
Transform a job description or natural language query into an optimized Google search string that finds LinkedIn profiles matching specific role requirements, experience levels, and geographic locations.

## Input Format
**Primary Input:** `{jd_content}` - Either:
1. **Complete Job Description** (preferred for accuracy)
2. **Natural Language Query** (for quick searches)

## Core Requirements
Generate a single, complete Google search query using these mandatory elements:

### 1. Site Targeting
- Always include: `site:linkedin.com/in/`

### 2. Job Title Identification
- Use `intitle:("Primary Title" OR "Alternative Title" OR "Related Title")`
- Extract 2-4 most relevant job titles from the input
- Include both exact titles and common variations

### 3. Experience Level Specification
- Include explicit experience indicators using `AND` operator
- Format: `("X years experience" OR "X+ years" OR "X-Y years")`
- Consider seniority levels: "junior", "senior", "lead", "principal" when appropriate

### 4. Geographic Targeting
- **ONLY if location is specified in the input:** Use `intext:("City" OR "State/Region")`
- Include primary location + broader regional alternatives
- Consider metro areas and nearby cities for better coverage
- **If NO location is mentioned:** Omit geographic targeting entirely

### 5. Key Skills/Technologies
- Extract 3-5 most critical skills from the input
- Use `AND (skill1 OR skill2 OR "skill phrase")`
- Prioritize technical skills, tools, and domain expertise

## Search Query Structure Template
**With Location:**
```
site:linkedin.com/in/ intitle:("Title1" OR "Title2") AND ("X years experience" OR "X+ years") AND intext:("Location1" OR "Region1") AND (skill1 OR skill2 OR "skill phrase")
```

**Without Location:**
```
site:linkedin.com/in/ intitle:("Title1" OR "Title2") AND ("X years experience" OR "X+ years") AND (skill1 OR skill2 OR "skill phrase")
```

## Processing Instructions
1. **Analyze the input** to extract:
   - Primary job role and alternatives
   - Required experience level or range
   - Geographic preferences
   - Essential skills and technologies

2. **Prioritize elements** by importance:
   - Core job function (highest priority)
   - Experience level (high priority - if specified)
   - Location (high priority - if specified)
   - Specific skills (medium priority)

3. **Handle missing information:**
   - If no experience level mentioned: omit experience criteria
   - If no location mentioned: omit geographic targeting
   - If minimal skills listed: focus on job title variations
4. **Optimize for coverage** by including:
   - Job title variations and industry synonyms
   - Experience level ranges (e.g., if 5 years required, include 4 years) - only if specified(stricly do't use -)
   - Regional alternatives to city names - only if location mentioned

4. **Balance specificity** with results:
   - Too specific = few results
   - Too broad = irrelevant results

## Quality Checks
- Ensure the query targets LinkedIn profiles specifically
- Include job title variations (always required)
- Only include experience criteria if mentioned in input
- Only include location targeting if specified in input
- Use proper Boolean operators (AND, OR)
- Include exact phrases in quotes when appropriate
- Keep query length manageable (under 200 characters when possible)

## Example Transformation

**Input:**
```
"We are looking for a highly motivated Marketing Manager with 5-7 years of experience to join our team in Bangalore. The ideal candidate will have strong digital marketing skills, experience with SEO/SEM, content strategy, and team leadership."
```

**Output:**
```
site:linkedin.com/in/ intitle:("Marketing Manager" OR "Digital Marketing Manager" OR "Marketing Lead") AND ("5 years experience" OR "6 years experience" OR "7 years experience" OR "5+ years") AND intext:("Bangalore" OR "Bengaluru" OR "Karnataka") AND (SEO OR SEM OR "content strategy" OR "digital marketing")
```

## Output Format
**IMPORTANT:** Provide ONLY the Google search query string. No explanations, no additional text, no formatting - just the raw search query.

## Input to Process
{jd_content} """
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        print(response.text.strip())
        return response.text.strip()
    except Exception as e:
        print(f"Error extracting JD requirements: {e}")
        return None

def search_and_store_profiles(jd_content: str, company=None):
    """
    Search for LinkedIn profiles based on job description and store results in database.
    
    Args:
        jd_content (str): Job description or search query
        company (Company): The company to associate with the profiles
        
    Returns:
        dict: Search results with stored profile data
    """
    # Generate search query using Gemini
    search_query = extract_jd_requirements(jd_content)
    if not search_query:
        return {'error': 'Failed to generate search query'}
    
    try:
        # Search using Google Serper API
        conn = http.client.HTTPSConnection("google.serper.dev")
        payload = json.dumps({
            "q": search_query
        })
        headers = {
            'X-API-KEY': os.getenv("SERPER_API_KEY"),
            'Content-Type': 'application/json'
        }
        
        conn.request("POST", "/search", payload, headers)
        res = conn.getresponse()
        response_data = res.read().decode("utf-8")
        data = json.loads(response_data)
        
        # Process and store results
        results = []
        if 'organic' in data:
            if not company:
                return {'error': 'Company is required to store LinkedIn profiles'}

            for result in data['organic']:
                linkedin_id = extract_linkedin_id(result.get('link', ''))
                if linkedin_id:
                    # Create or update LinkedIn profile in database
                    profile, created = LinkedInProfile.objects.update_or_create(
                        linkedin_id=linkedin_id,
                        company=company,
                        defaults={
                            'title': result.get('title', ''),
                            'subtitle': result.get('subtitle', ''),
                            'link': result.get('link', ''),
                            'snippet': result.get('snippet', ''),
                            'position': result.get('position', 0),
                            'search_query': search_query
                        }
                    )
                    
                    results.append({
                        'linkedin_id': linkedin_id,
                        'title': profile.title,
                        'subtitle': profile.subtitle,
                        'link': profile.link,
                        'snippet': profile.snippet,
                        'position': profile.position,
                        'created_at': profile.created_at,
                        'updated_at': profile.updated_at
                    })
        
        return data  # Return the complete Serper API response
        
    except Exception as e:
        print(f"Error in search_and_store_profiles: {str(e)}")
        return {'error': f'Error processing request: {str(e)}'}