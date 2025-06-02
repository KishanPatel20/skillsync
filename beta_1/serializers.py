from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .models import (
    Candidate, Experience, Skill, CandidateSkill, Project, AISummary,
    Company, HRProfile, ActivityLog, CandidateStatusLog
)

class AuthTokenSerializer(serializers.Serializer):
    """
    Serializer for obtaining authentication token.
    """
    username = serializers.CharField(
        label="Username",
        write_only=True
    )
    password = serializers.CharField(
        label="Password",
        style={'input_type': 'password'},
        trim_whitespace=False,
        write_only=True
    )

    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')

        if username and password:
            user = authenticate(request=self.context.get('request'),
                              username=username, password=password)

            if not user:
                msg = 'Unable to log in with provided credentials.'
                raise serializers.ValidationError(msg, code='authorization')
            
            if not user.is_active:
                msg = 'User account is disabled.'
                raise serializers.ValidationError(msg, code='authorization')
        else:
            msg = 'Must include "username" and "password".'
            raise serializers.ValidationError(msg, code='authorization')

        attrs['user'] = user
        return attrs

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'name', 'size', 'website', 'linkedin_url', 'location']

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    company_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'company_id']

    def create(self, validated_data):
        company_id = validated_data.pop('company_id')
        company = Company.objects.get(id=company_id)
        
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        
        # Create HR profile
        HRProfile.objects.create(user=user, company=company)
        
        return user

class ExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Experience
        fields = ['id', 'role', 'company', 'start_date', 'end_date', 'description']

class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ['id', 'skill_name']

class CandidateSkillSerializer(serializers.ModelSerializer):
    skill = SkillSerializer(read_only=True)
    
    class Meta:
        model = CandidateSkill
        fields = ['id', 'skill', 'years_of_experience']

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name', 'description']

class CandidateSerializer(serializers.ModelSerializer):
    experiences = ExperienceSerializer(many=True, read_only=True)
    skills = CandidateSkillSerializer(source='candidateskill_set', many=True, read_only=True)
    projects = ProjectSerializer(many=True, read_only=True)
    
    class Meta:
        model = Candidate
        fields = [
            'id', 'name', 'email', 'phone', 'linkedin_url', 'github_url',
            'resume_file_path', 'status', 'company', 'created_at',
            'last_status_update', 'experiences', 'skills', 'projects'
        ]
        read_only_fields = ['created_at', 'last_status_update']

class AISummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = AISummary
        fields = ['id', 'candidate', 'job_description_hash', 'summary_text', 'score', 'details_json', 'created_at']
        read_only_fields = ['created_at']

class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = ['id', 'user', 'company', 'activity_type', 'details_json', 'timestamp']
        read_only_fields = ['timestamp']

class CandidateStatusLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateStatusLog
        fields = ['id', 'candidate', 'user', 'old_status', 'new_status', 'notes', 'timestamp']
        read_only_fields = ['timestamp']

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
