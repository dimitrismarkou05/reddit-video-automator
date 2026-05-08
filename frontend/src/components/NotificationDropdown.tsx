import React, { useState, useEffect, useRef, useCallback } from "react";
import { Bell, Check, Trash2, AlertTriangle } from "lucide-react";
import { useNotificationStore } from "@/store";
import { notificationApi, sse } from "@/services/api";
import { formatDistanceToNow } from "date-fns";
import type { Notification } from "@/types";

export function NotificationDropdown() {
  const [isOpen, setIsOpen] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const {
    notifications,
    unreadCount,
    setNotifications,
    addNotification,
    markAsRead,
    markAllAsRead,
    removeNotification,
    clearAll,
  } = useNotificationStore();

  // Extract fetchNotifications as reusable callback
  const fetchNotifications = useCallback(async () => {
    try {
      const { data } = await notificationApi.list(false, 20);
      setNotifications(data);
    } catch (e) {
      console.error("Failed to fetch notifications:", e);
    }
  }, [setNotifications]);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  useEffect(() => {
    sse.connect("/api/v1/sse/notifications");
    sse.on("notification", (data) => {
      addNotification(data as Notification);
    });
    // Don't disconnect on unmount — keep SSE alive globally
    // return () => sse.disconnect();
  }, [addNotification]);

  // Poll every 10 seconds as fallback for missed SSE messages
  useEffect(() => {
    const interval = setInterval(fetchNotifications, 10000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setShowDeleteConfirm(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleMarkRead = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await notificationApi.markRead(id);
      markAsRead(id);
    } catch (e) {
      console.error("Failed to mark notification as read:", e);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await notificationApi.markAllRead();
      markAllAsRead();
    } catch (e) {
      console.error("Failed to mark all as read:", e);
    }
  };

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await notificationApi.delete(id);
      removeNotification(id);
    } catch (e) {
      console.error("Failed to delete notification:", e);
    }
  };

  const handleDeleteAll = async () => {
    try {
      await notificationApi.deleteAll(); // Single API call
      clearAll();
      setShowDeleteConfirm(false);
    } catch (e) {
      console.error("Failed to delete all notifications:", e);
    }
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case "error":
        return "bg-red-500";
      case "warning":
        return "bg-yellow-500";
      case "success":
        return "bg-green-500";
      default:
        return "bg-blue-500";
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="cursor-pointer relative p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-96 bg-surface-light dark:bg-surface-dark rounded-xl shadow-lg border border-border-light dark:border-border-dark z-50 overflow-hidden">
          <div className="flex items-center justify-between p-3 border-b border-border-light dark:border-border-dark">
            <h3 className="font-semibold">Notifications</h3>
            <div className="flex items-center gap-1">
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="cursor-pointer text-xs text-primary hover:text-primary-dark flex items-center gap-1 px-2 py-1 rounded-md hover:bg-primary/10 transition-colors"
                  title="Mark all as read"
                >
                  <Check className="w-3 h-3" />
                  Mark all read
                </button>
              )}
              {notifications.length > 0 && (
                <>
                  {showDeleteConfirm ? (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setShowDeleteConfirm(false)}
                        className="cursor-pointer text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 px-2 py-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleDeleteAll}
                        className="cursor-pointer text-xs text-red-600 hover:text-red-700 flex items-center gap-1 px-2 py-1 rounded-md bg-red-50 dark:bg-red-900/30 hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors"
                      >
                        <AlertTriangle className="w-3 h-3" />
                        Confirm
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setShowDeleteConfirm(true)}
                      className="cursor-pointer text-xs text-red-500 hover:text-red-600 flex items-center gap-1 px-2 py-1 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                      title="Delete all notifications"
                    >
                      <Trash2 className="w-3 h-3" />
                      Delete all
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                <Bell className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>No notifications yet</p>
              </div>
            ) : (
              notifications.map((notification) => (
                <div
                  key={notification.id}
                  className={`p-3 border-b border-border-light dark:border-border-dark hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors ${
                    !notification.is_read
                      ? "bg-primary/5 dark:bg-primary/10"
                      : ""
                  }`}
                  onClick={() =>
                    handleMarkRead(notification.id, {
                      stopPropagation: () => {},
                    } as any)
                  }
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`w-2 h-2 rounded-full mt-2 shrink-0 ${getLevelColor(notification.level)}`}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">
                        {notification.message}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {formatDistanceToNow(
                          new Date(notification.created_at),
                          { addSuffix: true },
                        )}
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      {!notification.is_read && (
                        <button
                          onClick={(e) => handleMarkRead(notification.id, e)}
                          className="cursor-pointer p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
                          title="Mark as read"
                        >
                          <Check className="w-3 h-3" />
                        </button>
                      )}
                      <button
                        onClick={(e) => handleDelete(notification.id, e)}
                        className="cursor-pointer p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-400"
                        title="Delete"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
