from django.contrib import admin
from .models import Review, Bundle, ReviewerStats

class ReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'submission', 'reviewer', 'rating', 'feels_ai_flag', 'created_at')
    list_filter = ('rating', 'feels_ai_flag')
    search_fields = ('reviewer__email', 'justification_text')

admin.site.register(Review, ReviewAdmin)
admin.site.register(Bundle)
admin.site.register(ReviewerStats)
