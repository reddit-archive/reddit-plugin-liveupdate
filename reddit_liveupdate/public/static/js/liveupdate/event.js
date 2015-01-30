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
      this.$resourcesEl = $('#liveupdate-resources')

      if (!this.$descriptionEl.length) {
        this.$descriptionEl = $('<div id="liveupdate-description">')
      }

      if (!this.$resourcesEl.length) {
        this.$resourcesEl = $('<section id="liveupdate-resources">')
        this.$resourcesEl.append($('<h2>' + r._('resources') + '</h2>'))
      }

      this.listenTo(this.model, {
        'change:title': this.renderTitle,
        'change:description_html': this.renderDescription,
        'change:resources_html': this.renderResources,
      })
    },

    renderTitle: function() {
      this.$titleEl.text(this.model.get('title'))
    },

    renderDescription: function() {
      var description = this.model.get('description_html')
      if (!description) {
        this.$descriptionEl.remove()
        return
      }

      this.$descriptionEl
        .html(description)
        .insertAfter(this.$titleEl)
    },

    renderResources: function() {
      var resources = this.model.get('resources_html')
      var $fragment

      if (!resources) {
        this.$resourcesEl.remove()
        return
      }

      this.$resourcesEl.find('.md').replaceWith($.parseHTML(resources))
      this.$resourcesEl.insertAfter('.sidebar-expand')
    },
  })
}(r, Backbone, jQuery)
