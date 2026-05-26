from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, SocialAccount, Hold, Strike

class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Platform Details', {'fields': ('role', 'status', 'country', 'fingerprint_hash')}),
        ('Payout Setup', {'fields': ('payout_method', 'payout_handle')}),
    )
    list_display = ('username', 'email', 'role', 'status', 'country', 'date_joined')
    list_filter = ('role', 'status', 'country')
    search_fields = ('username', 'email', 'fingerprint_hash')

admin.site.register(User, CustomUserAdmin)
admin.site.register(SocialAccount)
admin.site.register(Hold)
admin.site.register(Strike)
