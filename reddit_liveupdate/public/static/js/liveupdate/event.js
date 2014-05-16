!function(r, Backbone, $) {
  'use strict'

  var exports = r.liveupdate.event = {}

  exports.LiveUpdateEvent = Backbone.Model.extend({
    defaults: {
      'socket_state': 'connecting',
    },

    url: function() {
      return '/live/' + r.config.liveupdate_event + '/about.json'
    },

    parse: function(response) {
      return response.data
    },
  })

  exports.LiveUpdateEventView = Backbone.View.extend({
    initialize: function() {
      this.$titleEl = $('#liveupdate-title')
      this.$descriptionEl = $('#liveupdate-description')

      this.listenTo(this.model, {
        'change:title': this.renderTitle,
        'change:description_html': this.renderDescription,
      })
    },

    renderTitle: function() {
      this.$titleEl.text(this.model.get('title'))
    },

    renderDescription: function() {
      var description

      if (!this.$descriptionEl.length) {
        this.$descriptionEl = $('<section id="liveupdate-description" class="md">')
      }

      description = this.model.get('description_html')
      if (!description) {
        this.$descriptionEl.remove()
        return
      }

      this.$descriptionEl
        .html(description)
        .prependTo('aside.sidebar')
    },
  })
}(r, Backbone, jQuery)
