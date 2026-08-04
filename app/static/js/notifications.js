function attachNotificationHandlers() {
  // JOIN or REQUEST to join based on invite type
  document.querySelectorAll('.join-btn').forEach((button) => {
    button.addEventListener('click', () => {
      const notifId = button.getAttribute('data-id');

      fetch('/api/notif/get_notifications')
        .then((res) => res.json())
        .then((data) => {
          const notif = data.notifications.find((n) => n.id == notifId);
          if (!notif) throw new Error('Notification not found');

          const cliqueId = notif.clique_id;
          const type = notif.type;

          if (type === 'invitation' || type === 'invitation admin') {
            // Direct join
            return fetch(`/clique/join_clique/${cliqueId}`, { method: 'POST' })
              .then((res) => res.json())
              .then((data) => {
                alert(data.message || 'Joined!');
                return fetch(`/api/notif/delete_notification/${notifId}`, { method: 'POST' });
              })
              .then(() => {
                location.reload(); // Reload the page to show the new clique on the map
              });
          }

          if (type === 'invitation protected') {
            return fetch(`/clique/request_join_protected/${cliqueId}`, { method: 'POST' })
              .then((res) => res.json())
              .then((data) => {
                alert(data.message || 'Request sent to admin.');
                return fetch(`/api/notif/delete_notification/${notifId}`, { method: 'POST' });
              });
          }

          throw new Error('Unsupported notification type.');
        })
        .then(() => {
          button.closest('.notification-item').remove();
          if (document.querySelectorAll('.notification-item').length === 0) {
            refreshNotificationList();
          }
        })
        .catch((err) => {
          console.error('Join error:', err);
          alert('Something went wrong while processing the invitation.');
        });
    });
  });

  document.querySelectorAll('.decline-request').forEach((button) => {
    button.addEventListener('click', () => {
      const notifId = button.getAttribute('data-id');

      const confirmed = confirm('Are you sure you want to decline this request?');
      if (!confirmed) return;

      fetch(`/api/notif/delete_notification/${notifId}`, { method: 'POST' }).then(() => {
        button.closest('.notification-item').remove();
        if (document.querySelectorAll('.notification-item').length === 0) {
          refreshNotificationList();
        }
      });
    });
  });

  document.querySelectorAll('.accept-request').forEach((button) => {
    button.addEventListener('click', () => {
      const notifId = button.getAttribute('data-id');
      const cliqueId = button.getAttribute('data-clique');

      fetch(`/clique/accept_request/${notifId}/${cliqueId}`, { method: 'POST' })
        .then((res) => res.json())
        .then((data) => {
          alert(data.message || 'Request accepted.');
          button.closest('.notification-item').remove();
          if (document.querySelectorAll('.notification-item').length === 0) {
            refreshNotificationList();
          }
        });
    });
  });

  document.querySelectorAll('.ignore-btn').forEach((button) => {
    button.addEventListener('click', () => {
      const notifId = button.getAttribute('data-id');

      fetch(`/api/notif/delete_notification/${notifId}`, { method: 'POST' }).then(() => {
        button.closest('.notification-item').remove();
        if (document.querySelectorAll('.notification-item').length === 0) {
          refreshNotificationList();
        }
      });
    });
  });

  document.querySelectorAll('.request-btn').forEach((button) => {
    button.addEventListener('click', () => {
      const cliqueId = button.getAttribute('data-clique');
      const notifId = button.getAttribute('data-id');

      fetch(`/clique/request_join_protected/${cliqueId}`, { method: 'POST' })
        .then((res) => res.json())
        .then((data) => {
          alert(data.message || 'Request sent.');
          return fetch(`/api/notif/delete_notification/${notifId}`, { method: 'POST' });
        })
        .then(() => {
          button.closest('.notification-item').remove();
          if (document.querySelectorAll('.notification-item').length === 0) {
            refreshNotificationList();
          }
        });
    });
  });
}

function refreshNotificationList() {
  const list = document.getElementById('notifications-list');
  fetch('/api/notif/get_notifications')
    .then((res) => res.json())
    .then((data) => {
      list.innerHTML = '';

      const bell = document.getElementById('notificationBell');
      if (bell) {
        const hasNotifications = data.notifications.length > 0;
        const currentColor = getComputedStyle(bell).color;
        const targetColor = hasNotifications ? 'gold' : 'gray';
        bell.style.color = targetColor;
      }
      if (data.notifications.length === 0) {
        list.innerHTML = "<div class='notification-item'>No notifications</div>";
        return;
      }

      data.notifications.forEach((notif) => {
        const item = document.createElement('div');
        item.className = 'notification-item';
        const type = notif.type;
        const cliqueName = notif.clique_name;
        const cliqueId = notif.clique_id;
        let text = '';
        const cliqueVisibility = notif.visibility == 'Public' ? 'public' : notif.visibility == 'Private' ? 'private' : 'protected';

        if (type === 'invitation') {
          text = `Invited to join ${cliqueVisibility} clique <strong>${cliqueName}</strong>`;
          item.innerHTML = `
            ${text}
            <div class="notification-actions">
              <button class="btn btn-sm btn-success join-btn" data-id="${notif.id}" data-clique="${cliqueId}">Join</button>
              <button class="btn btn-sm btn-secondary ignore-btn" data-id="${notif.id}">Ignore</button>
            </div>`;
        } else if (type === 'invitation admin') {
          text = `Invited to join protected clique <strong>${cliqueName}</strong> (by admin)`;
          item.innerHTML = `
            ${text}
            <div class="notification-actions">
              <button class="btn btn-sm btn-success join-btn" data-id="${notif.id}" data-clique="${cliqueId}">Join</button>
              <button class="btn btn-sm btn-secondary ignore-btn" data-id="${notif.id}">Ignore</button>
            </div>`;
        } else if (type === 'invitation protected') {
          text = `Invited to join protected clique <strong>${cliqueName}</strong>`;
          item.innerHTML = `
            ${text}
            <div class="notification-actions">
              <button class="btn btn-sm btn-warning request-btn" data-id="${notif.id}" data-clique="${cliqueId}">Request to Join</button>
              <button class="btn btn-sm btn-secondary ignore-btn" data-id="${notif.id}">Ignore</button>
            </div>`;
        } else if (type === 'request to join protected') {
          const requester = notif.requester_name || 'A user';
          text = `<strong>${requester}</strong> requested to join protected clique <strong>${cliqueName}</strong>`;
          item.innerHTML = `
            ${text}
            <div class="notification-actions">
              <button class="btn btn-sm btn-success accept-request" data-id="${notif.id}" data-clique="${cliqueId}">Accept</button>
              <button class="btn btn-sm btn-danger decline-request" data-id="${notif.id}">Decline</button>
            </div>`;
        } else if (type == 'accept invitation') {
          item.innerHTML = `
            <div>Your request to join <strong>${cliqueName}</strong> has been accepted by the admin.</div>
            <div class="notification-actions">
              <button class="btn btn-sm btn-secondary ignore-btn" data-id="${notif.id}">Okay</button>
            </div>
          `;
        } else if (type === 'ban') {
          item.innerHTML = `
            <div>You were banned from <strong>${cliqueName}</strong>.</div>
            <div class="notification-actions">
              <button class="btn btn-sm btn-secondary ignore-btn" data-id="${notif.id}">Okay</button>
            </div>
          `;
        } else if (type === 'unban') {
          item.innerHTML = `
            <div>You were unbanned from <strong>${cliqueName}</strong>. You may now rejoin.</div>
            <div class="notification-actions">
              <button class="btn btn-sm btn-secondary ignore-btn" data-id="${notif.id}">Okay</button>
            </div>
          `;
        } else if (type === 'kick') {
          item.innerHTML = `
            <div>You were removed from <strong>${cliqueName}</strong>.</div>
            <div class="notification-actions">
              <button class="btn btn-sm btn-secondary ignore-btn" data-id="${notif.id}">Okay</button>
            </div>
          `;
        } else if (type === 'invitation to become admin') {
          text = `You've been invited to become the admin of <strong>${cliqueName}</strong>`;
          item.innerHTML = `
            ${text}
            <div class="notification-actions">
              <form method="POST" action="/clique/accept_admin_invite/${notif.id}/${cliqueId}" style="display: inline;">
                <button class="btn btn-sm btn-success">Accept</button>
              </form>
              <form method="POST" action="/clique/decline_admin_invite/${notif.id}" style="display: inline;">
                <button class="btn btn-sm btn-secondary">Decline</button>
              </form>
            </div>
          `;
        } else if (type === 'admin replacement') {
          item.innerHTML = `
            <div>You have been made the admin of <strong>${cliqueName}</strong> because the previous admin left the clique.</div>
            <div class="notification-actions">
              <button class="btn btn-sm btn-secondary ignore-btn" data-id="${notif.id}">Okay</button>
            </div>
          `;
        }

        list.appendChild(item);
      });

      attachNotificationHandlers(); // Rebind buttons
    });
}

function setupNotificationDropdown() {
  const notifIcon = document.getElementById('notificationsDropdown');
  const notifMenu = document.querySelector('.notifications-menu');

  if (notifIcon && notifMenu) {
    notifIcon.addEventListener('click', () => {
      notifMenu.style.display = notifMenu.style.display === 'block' ? 'none' : 'block';

      if (notifMenu.style.display === 'block') {
        refreshNotificationList();
      }
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    setupNotificationDropdown();
    refreshNotificationList();
  });
} else {
  setupNotificationDropdown();
  refreshNotificationList();
}
