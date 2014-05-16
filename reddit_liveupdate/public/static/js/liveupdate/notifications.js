!function(r, Backbone, $, _, store) {
  'use strict'

  var exports = r.liveupdate.notifications = {}
  var NOTIFICATION_TTL_SECONDS = 10

  function ellipsize(text, limit) {
    if (text.length > limit) {
      return text.substring(0, limit) + '…'
    }
    return text
  }

  exports.DesktopNotifier = Backbone.View.extend({
    tagName: 'input',
    attributes: {
      'type': 'checkbox',
    },

    events: {
      'change': 'onSettingsChange',
    },

    initialize: function() {
      this.storageKey = 'live.' + r.config.liveupdate_event + '.notifications'
      this.requestingPermission = false
      if (Notification.permission === 'granted') {
        this.notificationsDesired = store.safeGet(this.storageKey)
      } else {
        this.notificationsDesired = false
      }
      this.notifications = []
      this.listenTo(this.model, 'add', this.onNewUpdate)
      $(document).on('visibilitychange', $.proxy(this, 'onVisibilityChange'))
    },

    shouldNotify: function() {
      return (
          this.notificationsDesired &&
          Notification.permission === 'granted' &&
          document.hidden
      )
    },

    onNewUpdate: function(update, collection, options) {
      // not a new update, just scrollin'
      if (options.at !== 0) {
        return
      }

      // don't want to notify anyway
      if (!this.shouldNotify()) {
        return
      }

      // never notify a user about their own posts
      if (update.get('author') === r.config.logged) {
        return
      }

      var _this = this
      var titleText = $('#liveupdate-title').text()
      var bodyText = $($.parseHTML(update.get('body'))).text()
      var notification = new Notification(titleText, {
        body: ellipsize(bodyText, 160),
        icon: r.utils.staticURL('liveupdate-notification-icon.png'),
      })
      this.notifications.push(notification)

      notification.onclick = function(ev) {
        window.focus()
        ev.preventDefault()
      }

      notification.onclose = function(ev) {
        var index = _this.notifications.indexOf(ev.target)
        _this.notifications.splice(index, 1)
      }

      setTimeout(function() {
        notification.close()
      }, NOTIFICATION_TTL_SECONDS * 1000)
    },

    onVisibilityChange: function() {
      if (!document.hidden) {
        this.clearNotifications()
      }
    },

    onSettingsChange: function() {
      this.notificationsDesired = this.$el.prop('checked')

      store.safeSet(this.storageKey, this.notificationsDesired)

      if (this.notificationsDesired && Notification.permission !== 'granted') {
        this.requestPermission()
      }
    },

    requestPermission: function() {
      this.requestingPermission = true

      Notification.requestPermission(_.bind(this.onPermissionChange, this))

      this.render()
    },

    onPermissionChange: function() {
      this.requestingPermission = false
      this.render()
    },

    clearNotifications: function() {
      _.invoke(this.notifications, 'close')
    },

    render: function() {
      this.$el
        .prop('disabled', this.requestingPermission || Notification.permission === 'denied')
        .prop('checked', this.notificationsDesired)
      return this
    },
  })
}(r, Backbone, jQuery, _, store)
