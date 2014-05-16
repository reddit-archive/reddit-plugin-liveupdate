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
        var $link = $el.find('a[href="' + embed.url + '"]')
        var embedUri = this._embedBase + '/' + updateId + '/' + embedIndex
        var iframe = $('<iframe>').attr({
          'class': 'embedFrame embed-' + embedIndex,
          'src': embedUri,
          'width': embed.width,
          'height': embed.height || 200,
          'scrolling': 'no',
          'frameborder': 0,
        })
        r.debug('Rendering embed for link: ', $link)
        $link.replaceWith(iframe)
      }, this)
    },

    _handleMessage: function(e) {
      var ev = e.originalEvent

      if (ev.origin.replace(/^https?:\/\//,'') !== r.config.media_domain) {
        return false
      }

      var data = JSON.parse(ev.data)
      var $embedFrame

      if (data.action === 'dimensionsChange') {
        // Yuck. A good reason to give embeds unique IDs.
        $('.id-LiveUpdate_' + data.updateId + ' .embed-' + data.embedIndex)
          .attr({
            'width': Math.min(data.width, 480),
            'height': data.height,
          })
      }
    },
  })
}(r, Backbone, jQuery, _)
