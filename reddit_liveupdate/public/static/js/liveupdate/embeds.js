!function(r, Backbone, $, _) {
  'use strict'

  var exports = r.liveupdate.embeds = {}

  // EmbedViewer displays matching embeddable links inline nicely for live
  // updates (like tweets).
  //
  // Workflow:
  //
  // 1. On scroll, see if updates with pending embeds are in the viewport
  //    (denoted by .pending-embed).
  // 2. For each of those updates, load all of the embeds within the update and
  //    replace them with their iframes.
  //
  exports.EmbedViewer = r.ScrollUpdater.extend({
    selector: '.pending-embed',

    initialize: function() {
      this._embedBase = ('//' + r.config.media_domain +
        '/mediaembed/liveupdate/' + r.config.liveupdate_event)

      this.listenTo(this.model, 'add', this.restart)

      r.ScrollUpdater.prototype.initialize.apply(this, arguments)
    },

    _listen: function() {
      $(window).on('message', $.proxy(this, '_handleMessage'))
      r.ScrollUpdater.prototype._listen.apply(this, arguments)
    },

    update: function($el) {
      var updateId = $el.data('fullname')
      var embeds = this.model.get(updateId).get('embeds')

      if (!$el.hasClass('pending-embed')) {
        return
      }
      $el.removeClass('pending-embed')

      _.each(embeds, function(embed, embedIndex) {
        var $placeholder = $el
          .find('p')
          .has('a[href="' + embed.url + '"]')
          .filter(function() {
            return $(this).contents().length === 1
          })
        var embedUri = this._embedBase + '/' + updateId + '/' + embedIndex
        var iframe = $('<iframe>').attr({
          'class': 'embedFrame',
          'id': 'embed-' + updateId + '-' + embedIndex,
          'src': embedUri,
          'height': embed.height || 200,
          'scrolling': 'no',
          'frameborder': 0,
          'allowfullscreen': true,
        })
        r.debug('Rendering embed for link: ', embed.url)
        $placeholder.replaceWith(iframe)
      }, this)
    },

    _handleMessage: function(e) {
      var ev = e.originalEvent

      if (ev.origin.replace(/^https?:\/\//,'') !== r.config.media_domain) {
        return false
      }

      var data;
      try {
        data = JSON.parse(ev.data)
      } catch (e) {
        // Message probably intended for another consumer
        return false
      }
      if (typeof data.updateId === 'undefined' || typeof data.embedIndex === 'undefined') {
        // Message probably intended for another consumer
        return false
      }

      var $embedFrame = $('#embed-LiveUpdate_' + data.updateId + '-' + data.embedIndex)

      if (data.action === 'dimensionsChange') {
          $embedFrame.attr({
            'height': data.height,
          })
      }
    },
  })
}(r, Backbone, jQuery, _)
