from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from dateutil import parser
import datetime

class Company(models.Model):
    name = models.CharField(max_length=255, unique=True, help_text="Name of the company.")
    size = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=[
            ("1-50", "1-50 employees"),
            ("51-250", "51-250 employees"),
            ("251-1000", "251-1000 employees"),
            ("1000+", "1000+ employees"),
        ],
        help_text="Size of the company based on employee count.",
    )
    website = models.URLField(blank=True, null=True, help_text="Company's official website URL.")
    linkedin_url = models.URLField(blank=True, null=True, help_text="Company's LinkedIn profile URL.")
    location = models.CharField(max_length=255, blank=True, null=True, help_text="Primary location of the company.")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Companies"
        ordering = ["name"]

    def __str__(self):
        return self.name

class HRProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='hr_profile', help_text="Django User associated with this HR profile.")
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='hr_users', help_text="The company this HR user belongs to.")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.company.name})"

class Candidate(models.Model):
    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('REVIEW', 'Under Review'),
        ('SELECTED', 'Selected'),
        ('REJECTED', 'Rejected'),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='candidates', help_text="The company associated with this candidate.")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='NEW',
        help_text="Current status of the candidate within the hiring process."
    )
    last_status_update = models.DateTimeField(default=timezone.now, help_text="Timestamp of the last status change.")
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    github_url = models.URLField(blank=True, null=True)
    resume_file_path = models.CharField(max_length=512, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_candidates')

    class Meta:
        unique_together = (('company', 'email'),)
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.company.name}) - {self.status}"

class Experience(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='experiences')
    role = models.CharField(max_length=255)
    company = models.CharField(max_length=255)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.role} at {self.company}"

class Skill(models.Model):
    skill_name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.skill_name

class CandidateSkill(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE)
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    years_of_experience = models.FloatField(blank=True, null=True)

    class Meta:
        unique_together = (('candidate', 'skill'),)

    def __str__(self):
        return f"{self.candidate.name} - {self.skill.skill_name}"

class Project(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=255 , blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class AISummary(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='ai_summaries')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ai_summaries_by_company')
    job_description_hash = models.CharField(max_length=128)
    summary_text = models.TextField()
    score = models.FloatField(blank=True, null=True)
    details_json = models.JSONField(default=dict, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_summaries')

    class Meta:
        unique_together = (('candidate', 'job_description_hash', 'company'),)
        verbose_name_plural = "AI Summaries"

    def __str__(self):
        return f"Summary for {self.candidate.name} ({self.job_description_hash})"

class LinkedInProfile(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='linkedin_search_results')
    linkedin_id = models.CharField(max_length=255, primary_key=True)
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255)
    link = models.URLField()
    snippet = models.TextField()
    position = models.IntegerField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    search_query = models.TextField()
    job_description_for_search = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['position']
        verbose_name_plural = "LinkedIn Profiles (Search Results)"

    def __str__(self):
        return f"{self.title} ({self.linkedin_id})"

class CandidateStatusLog(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='status_history')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='candidate_status_logs')
    old_status = models.CharField(max_length=20, choices=Candidate.STATUS_CHOICES, blank=True, null=True)
    new_status = models.CharField(max_length=20, choices=Candidate.STATUS_CHOICES)
    timestamp = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.candidate.name}: {self.old_status} -> {self.new_status}"

class ActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='activity_logs_by_company')
    activity_type = models.CharField(
        max_length=50,
        choices=[
            ('REGISTER', 'User Registration'),
            ('LOGIN', 'User Login'),
            ('LOGOUT', 'User Logout'),
            ('RESUME_UPLOAD', 'Resume Upload'),
            ('JD_SEARCH', 'Job Description Search'),
            ('LINKEDIN_SEARCH', 'LinkedIn Search'),
            ('PROFILE_SCRAPE', 'LinkedIn Profile Scrape'),
            ('PROFILE_ANALYZE', 'Profile Analysis'),
            ('CANDIDATE_STATUS_UPDATE', 'Candidate Status Update'),
            ('JD_SEARCH_ERROR', 'JD Search Error'),
            ('PROFILE_SCRAPE_ERROR', 'Profile Scrape Error'),
            ('LINKEDIN_SEARCH_ERROR', 'LinkedIn Search Error'),
            ('RESUME_UPLOAD_ERROR', 'Resume Upload Error'),
        ]
    )
    timestamp = models.DateTimeField(default=timezone.now)
    details_json = models.JSONField(default=dict, blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"

    def __str__(self):
        return f"{self.user.username} - {self.activity_type} at {self.timestamp}"


