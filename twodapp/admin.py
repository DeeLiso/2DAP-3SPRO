from django.contrib import admin

from .models import BettorAccount, ControlCenterAudit, GameState, OperationLog


@admin.register(GameState)
class GameStateAdmin(admin.ModelAdmin):
    list_display = ('slug', 'global_limit', 'total_amount', 'valid_lines', 'updated_at')


@admin.register(OperationLog)
class OperationLogAdmin(admin.ModelAdmin):
    list_display = ('formula', 'original', 'count', 'amount', 'is_error', 'created_at')
    list_filter = ('formula', 'is_error')


@admin.register(BettorAccount)
class BettorAccountAdmin(admin.ModelAdmin):
    list_display = ('username', 'phone', 'balance', 'multiplier', 'is_active', 'last_seen')
    list_filter = ('is_active', 'multiplier')
    search_fields = ('username', 'phone', 'last_ip')
    readonly_fields = ('password_hash', 'created_at')


@admin.register(ControlCenterAudit)
class ControlCenterAuditAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor_name', 'action', 'target_type', 'target_name')
    list_filter = ('action', 'target_type')
    search_fields = ('actor_name', 'target_name')
    readonly_fields = ('actor_id', 'actor_name', 'action', 'target_type', 'target_id', 'target_name', 'changes', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
