from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from lncrawler_api.models import ScheduledTask


@admin.register(ScheduledTask)
class ScheduledTaskAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'colored_status', 
        'interval_display', 
        'last_run_at', 
        'next_run_at', 
        'worker_info',
        'updated_at'
    ]
    list_filter = ['status', 'created_at']
    readonly_fields = [
        'created_at', 
        'updated_at', 
        'worker_id', 
        'locked_until',
        'last_run_at'
    ]
    search_fields = ['name', 'worker_id']
    
    fieldsets = (
        (None, {
            'fields': ('name', 'interval_seconds', 'status')
        }),
        ('Scheduling', {
            'fields': ('last_run_at', 'next_run_at'),
        }),
        ('Lock Info', {
            'fields': ('locked_until', 'worker_id'),
            'classes': ['collapse'],
        }),
        ('Error Info', {
            'fields': ('error_message',),
            'classes': ['collapse'],
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse'],
        }),
    )
    
    def colored_status(self, obj):
        colors = {
            'pending': '#ffc107',
            'running': '#007bff',
            'completed': '#28a745',
            'failed': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        
        status_text = obj.status
        if obj.locked_until and obj.locked_until > timezone.now():
            status_text += " (locked)"
        elif obj.locked_until and obj.locked_until <= timezone.now():
            status_text += " (STALE LOCK)"
            color = '#dc3545'  # Red for stale locks
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            status_text.upper()
        )
    colored_status.short_description = 'Status'
    
    def interval_display(self, obj):
        hours = obj.interval_seconds // 3600
        minutes = (obj.interval_seconds % 3600) // 60
        seconds = obj.interval_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    interval_display.short_description = 'Interval'
    
    def worker_info(self, obj):
        if obj.worker_id and obj.locked_until:
            if obj.locked_until > timezone.now():
                return format_html(
                    '<span style="color: #007bff;">{}</span>',
                    obj.worker_id
                )
            else:
                return format_html(
                    '<span style="color: #dc3545; text-decoration: line-through;">{}</span>',
                    obj.worker_id
                )
        return "-"
    worker_info.short_description = 'Worker'
    
    actions = ['reset_tasks', 'cleanup_stale_locks']
    
    def reset_tasks(self, request, queryset):
        count = 0
        for task in queryset:
            task.status = 'pending'
            task.locked_until = None
            task.worker_id = None
            task.error_message = ""
            task.save()
            count += 1
        
        self.message_user(request, f"Reset {count} tasks to pending state.")
    reset_tasks.short_description = "Reset selected tasks to pending state"
    
    def cleanup_stale_locks(self, request, queryset):
        count = 0
        for task in queryset.filter(locked_until__lt=timezone.now(), status='running'):
            task.status = 'pending'
            task.locked_until = None
            task.worker_id = None
            task.error_message = "Lock expired - cleaned up by admin"
            task.save()
            count += 1
        
        self.message_user(request, f"Cleaned up {count} stale locks.")
    cleanup_stale_locks.short_description = "Clean up stale locks in selected tasks"
