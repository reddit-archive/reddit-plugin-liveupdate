!function(r, Backbone, Tinycon, $) {
  'use strict'

  var exports = r.liveupdate.favicon = {}

  var FAVICON = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAMAAAAoLQ9TAAAA/1BMVEUpLzY+PDpGSk5HR0dKTlNSW2VTXGVVXmdWWl5bYWZdZGtfanVfbHpgXVtianNjbXhkZWdkam1lcX1nc4BpdYJqa2xscHZucHJueYRvfoxwfIhxcG93e4B3h5h4iJh5ipt7gIB8ipl+fn6BgYGImKOJh4aKjY2Mna6NobSOn7CQo7iar8Wfnp2juM6lo6Gmuc6mu8moqaqsw9etwcmurq6vrauxyN2xyN+0s7K+u7m/1u7C2vPF3fbI4PrJ4fvJ4/7Ly8vPzMnP6P7S0tLT0c/W8P/Z19Xd9/7d+P7e3Nrw8PDz9vT69/T+EA/+MjD+pqT+srD+w8H+zsz+/v7///9fla50AAAAuElEQVR42l2P2RaBUBhGT0WZ54jIPM8h0zE7SBL97/8uYoXFvtwXe30fIn8ggn94i8XMGSkFQvmPwFXvwOe/OGyx3OJYF+OUq26LcS2LMs05Xj0bPY+QDFc6k1bOnRQ8PYLiKlXW4IlWptQ4QWlxCIZ+h7tuwFBME9RgAG5XE8zrDYBpWNEEfElY0RO7Aejvzrs+wIa1xFGmp7AuFoprmNLya4fC8aP9YT/iOeX9pS1Fg1GpbZ/74wFo2jf64C4agwAAAABJRU5ErkJggg=='

  exports.UnreadUpdateCounter = Backbone.View.extend({
    initialize: function() {
      this.unreadItemCount = 0

      Tinycon.setOptions({
        'background': '#ff4500'
      })
      Tinycon.setImage(FAVICON)

      this.listenTo(this.model, 'add', this.onUpdateAdded)
      $(document).on('visibilitychange', $.proxy(this.onVisibilityChange, this))

      this.onVisibilityChange()
    },

    onUpdateAdded: function(update, collection, options) {
      if (options.at === 0 && document.hidden) {
        this.unreadItemCount += 1
        Tinycon.setBubble(this.unreadItemCount)
      }
    },

    onVisibilityChange: function() {
      if (!document.hidden) {
        Tinycon.setBubble()
        this.unreadItemCount = 0
      }
    },
  })
}(r, Backbone, Tinycon, jQuery)
