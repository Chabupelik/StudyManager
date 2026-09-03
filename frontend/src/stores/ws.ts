import { defineStore } from 'pinia';
import { ref } from 'vue';
import { appBridge } from '../utils/bridge';
import { useScheduleStore } from './schedule';
import { useAttendanceStore } from './attendance';
import { useDutyStore } from './duties';
import { useAdminStore } from './admin';

export const useWsStore = defineStore('ws', () => {
  const isConnected = ref(false);
  let socket: WebSocket | null = null;
  let reconnectTimeout: any = null;

  function connect() {
    if (socket && socket.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const url = `${protocol}//${host}/ws`;

    try {
      socket = new WebSocket(url);

      socket.onopen = () => {
        isConnected.value = true;
        // Отправляем auth payload (TG initData или VK query-строка)
        const payload = appBridge.getWsAuthPayload();
        if (socket && payload) {
          socket.send(payload);
        }
      };

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          handleIncomingMessage(msg);
        } catch (e) {
          console.error('WS parse error', e);
        }
      };

      socket.onclose = () => {
        isConnected.value = false;
        scheduleReconnect();
      };

      socket.onerror = () => {
        isConnected.value = false;
      };
    } catch (e) {
      console.error('WS connect error', e);
      scheduleReconnect();
    }
  }

  function scheduleReconnect() {
    if (reconnectTimeout) clearTimeout(reconnectTimeout);
    reconnectTimeout = setTimeout(() => {
      connect();
    }, 3000);
  }

  function handleIncomingMessage(msg: any) {
    const scheduleStore = useScheduleStore();
    const attendanceStore = useAttendanceStore();
    const dutyStore = useDutyStore();
    const adminStore = useAdminStore();

    switch (msg.type) {
      case 'update_attendance':
      case 'update_day':
      case 'override': {
        const msgDate = msg.date;
        if (msgDate) {
          scheduleStore.invalidateCache(msgDate);
          if (scheduleStore.dateKey === msgDate) {
            // Тихое обновление — без loading-индикатора, без мерцания
            scheduleStore.refreshSilently();
            if (attendanceStore.lessonTime) {
              attendanceStore.refreshDetailsSilently();
            }
          }
        }
        break;
      }

      case 'update_duties': {
        dutyStore.loadDuties();
        break;
      }

      case 'new_log': {
        if (msg.entry) {
          adminStore.logs.unshift(msg.entry);
        }
        break;
      }

      case 'admin_status': {
        adminStore.loadAdmins();
        break;
      }


    }
  }

  return {
    isConnected,
    connect,
  };
});
