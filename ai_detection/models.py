from django.db import models
from django.conf import settings

class StylometricBaseline(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stylometric_baseline')
    avg_sentence_length = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)
    vocabulary_diversity_score = models.DecimalField(max_digits=5, decimal_places=4, default=0.0)
    punctuation_signature = models.JSONField(default=dict, blank=True)
    built_from_submissions = models.ManyToManyField('submissions.Submission', related_name='stylometric_baselines')
    last_updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Baseline for {self.user.email} (vocab: {self.vocabulary_diversity_score})"
