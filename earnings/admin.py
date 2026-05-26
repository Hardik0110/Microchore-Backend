from django.contrib import admin
from .models import Earning, PayoutBatch

class EarningAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'project', 'amount', 'kind', 'status', 'payout_batch', 'created_at')
    list_filter = ('kind', 'status', 'project')
    search_fields = ('user__email', 'user__username')

class PayoutBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'period_start', 'period_end', 'total_amount', 'status', 'exported_at')
    list_filter = ('status', 'project')

admin.site.register(Earning, EarningAdmin)
admin.site.register(PayoutBatch, PayoutBatchAdmin)
