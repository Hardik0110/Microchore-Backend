from django.contrib import admin
from .models import AlertEvent, Metric

class AlertEventAdmin(admin.ModelAdmin):
    list_display = ('metric', 'value', 'threshold', 'severity', 'triggered_at', 'sent_to_discord_at')
    list_filter = ('severity', 'metric')

class MetricAdmin(admin.ModelAdmin):
    list_display = ('name', 'current_value', 'last_updated_at')

admin.site.register(AlertEvent, AlertEventAdmin)
admin.site.register(Metric, MetricAdmin)
