from rest_framework import serializers
from .models import Review

class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['rating', 'justification_text', 'feels_ai_flag', 'time_taken_seconds']

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError('Rating must be between 1 and 5.')
        return value

    def validate_justification_text(self, value):
        if len((value or '').strip()) < 30:
            raise serializers.ValidationError('Justification must be at least 30 characters long.')
        return value
