from django.db import models

class AlertEvent(models.Model):
    SEVERITY_CHOICES = (
        ('INFO', 'Information'),
        ('WARN', 'Warning'),
        ('CRIT', 'Critical Exception'),
    )

    metric = models.CharField(max_length=255)
    value = models.DecimalField(max_digits=12, decimal_places=4)
    threshold = models.DecimalField(max_digits=12, decimal_places=4)
    triggered_at = models.DateTimeField(auto_now_add=True)
    sent_to_discord_at = models.DateTimeField(null=True, blank=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='WARN')

    def __str__(self):
        return f"{self.severity}: {self.metric} reached {self.value} (Threshold: {self.threshold})"


class Metric(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    current_value = models.DecimalField(max_digits=15, decimal_places=4, default=0.0)
    last_updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Metric: {self.name} = {self.current_value}"
