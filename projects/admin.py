from django.contrib import admin
from .models import Company, Project, Task

class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'status', 'pay_rate_per_approved_task', 'payout_cadence', 'created_at')
    list_filter = ('status', 'payout_cadence', 'ai_detection_strictness')
    search_fields = ('name', 'brief_md')

class TaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'status', 'keyword', 'remaining_count', 'total_count', 'expires_at')
    list_filter = ('status', 'project')
    search_fields = ('keyword', 'target_post_url')

admin.site.register(Company)
admin.site.register(Project, ProjectAdmin)
admin.site.register(Task, TaskAdmin)
