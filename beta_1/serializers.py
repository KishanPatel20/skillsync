from rest_framework import serializers
from .models import Candidate, Experience, Skill, CandidateSkill, Project, AISummary

class CandidateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = '__all__'

class ExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Experience
        fields = '__all__'

class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = '__all__'

class CandidateSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateSkill
        fields = '__all__'

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = '__all__'

class AISummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = AISummary
        fields = '__all__' 

class CandidateFullSerializer(serializers.ModelSerializer):
    experiences = ExperienceSerializer(many=True, read_only=True)
    projects = ProjectSerializer(many=True, read_only=True)
    skills = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = [
            'id', 'name', 'email', 'phone', 'linkedin_url', 'github_url', 'resume_file_path',
            'experiences', 'skills', 'projects'
        ]

    def get_skills(self, obj):
        return [cs.skill.skill_name for cs in obj.candidateskill_set.all()]   
