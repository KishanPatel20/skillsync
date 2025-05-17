from django.db import models
from django.utils import timezone
from dateutil import parser
import datetime

class Candidate(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    linkedin_url = models.URLField(blank=True, null=True)
    github_url = models.URLField(blank=True, null=True)
    resume_file_path = models.CharField(max_length=512, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

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

    class Meta:
        unique_together = (('candidate', 'skill'),)

    def __str__(self):
        return f"{self.candidate.name} - {self.skill.skill_name}"

class Project(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='projects')
    project_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.project_name

class AISummary(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='ai_summaries')
    job_description_hash = models.CharField(max_length=128)
    summary_text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = (('candidate', 'job_description_hash'),)

    def __str__(self):
        return f"Summary for {self.candidate.name} ({self.job_description_hash})"


