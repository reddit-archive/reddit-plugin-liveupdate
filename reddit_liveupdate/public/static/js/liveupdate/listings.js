!function(r, Backbone, $) {
  'use strict'

  var exports = r.liveupdate.listings = {}

  var parseTimestamp = function(timestamp) {
    return moment(timestamp)
      .utc()
      .zone(-r.config.liveupdate_utc_offset)
  }

  var LiveUpdateTimeText = function() {
    r.TimeText.apply(this, arguments)
  }
  _.extend(LiveUpdateTimeText.prototype, r.TimeText.prototype, {
    formatTime: function($el, age, timestamp, now) {
      var daysOld = age / 60 / 60 / 24

      if (daysOld < 1 && !$el.hasClass('absolute')) {
        return r.TimeText.prototype.formatTime.apply(this, arguments)
      }

      timestamp = parseTimestamp(timestamp)
      now = parseTimestamp(now)

      if (timestamp.format('YYYY-MM-DD') == now.format('YYYY-MM-DD')) {
        return timestamp.format('LT')
      } else if (daysOld < 365) {
        return timestamp.format('D MMM LT')
      } else {
        return timestamp.format('lll')
      }
    },
  })

  var LiveUpdate = exports.LiveUpdate = Backbone.Model.extend({
    parse: function(response) {
      return {
        id: response.data.name,
        date: response.data.created_utc * 1000,
        author: response.data.author,
        stricken: response.data.stricken,
        body: response.data.body_html,
        embeds: response.data.embeds,
      }
    },

    _sendRPC: function(endpoint) {
      return r.ajax({
        type: 'POST',
        dataType: 'json',
        url: '/api/live/' + r.config.liveupdate_event + '/' + endpoint,
        data: {
          id: this.get('id'),
        },
      })
    },

    strike: function() {
      return this._sendRPC('strike_update')
    },

    destroy: function() {
      return this._sendRPC('delete_update')
    },
  })

  exports.LiveUpdateListing = Backbone.Collection.extend({
    model: LiveUpdate,

    url: function() {
      return '/live/' + r.config.liveupdate_event + '.json'
    },

    initialize: function() {
      this._updatesFetched = 0
      this.hasMoreToFetch = true
    },

    fetchMore: function() {
      var lastUpdateID = this.last().get('id')
      return this.fetch({
        remove: false,
        data: {
          'after': lastUpdateID,
          'count': this._updatesFetched,
        }
      })
    },

    parse: function(response) {
      var children = response.data.children

      this._updatesFetched += children.length
      this.hasMoreToFetch = !!response.data.after

      return children
    },
  })

  var LiveUpdateView = exports.LiveUpdateView = Backbone.View.extend({
    tagName: 'li',
    className: 'liveupdate',
    events: {
      'confirm .strike': 'onStrike',
      'confirm .delete': 'onDelete',
    },

    initialize: function(options) {
      this.permissions = options.permissions
      this.listenTo(this.model, {
        'change:stricken': this.onStrickenChange,
        'change:embeds': this.markPendingEmbeds,
      })
    },

    addEditButtonsIfAllowed: function() {
      if (this.model.get('author') === r.config.logged ||
          this.permissions.allow('edit')) {
        var $buttonRow = $('<ul class="buttonrow">')

        if (!this.model.get('stricken')) {
          $buttonRow.append(r.templates.make('liveupdate/edit-button', {
            name: 'strike',
            label: r._('strike'),
          }))
        }

        $buttonRow.append(r.templates.make('liveupdate/edit-button', {
          name: 'delete',
          label: r._('delete'),
        }))

        $buttonRow.find('button').each(function(index, el) {
          new r.ui.ConfirmButton({el: el})
        })

        this.$el.append($buttonRow)
      }
      return this
    },

    onStrickenChange: function() {
      this.$el
        .toggleClass('stricken', this.model.get('stricken'))

      if (this.model.get('stricken')) {
        this.$el.find('button.strike').remove()
      }

      return this
    },

    markPendingEmbeds: function() {
      this.$el.addClass('pending-embed')
    },

    render: function() {
      var time = parseTimestamp(this.model.get('date'))

      this.$el
        .data('fullname', this.model.get('id'))
        .html(r.templates.make('liveupdate/update', {
          body: this.model.get('body'),
          authorName: this.model.get('author'),
          isoDate: time.toISOString(),
          fullDate: time.format('LLL Z'),
        }))

      this
        .addEditButtonsIfAllowed()
        .onStrickenChange()

      if (this.model.get('embeds')) {
        this.markPendingEmbeds()
      }

      return this
    },

    onStrike: function() {
      var $button = this.$el.find('.strike.confirm-button')
      $button.text(r._('striking…'))
      this.model.strike()
        .done(function() {
          $button.text(r._('stricken'))
        })
    },

    onDelete: function() {
      var $button = this.$el.find('.strike.confirm-button')
      $button.text(r._('deleting…'))
      this.model.destroy()
        .done(function() {
          $button.text(r._('deleted'))
        })
    },
  })

  exports.LiveUpdateListingView = Backbone.View.extend({
    el: '.liveupdate-listing',

    initialize: function(options) {
      this.permissions = options.permissions
      this.timeText = new LiveUpdateTimeText({maxage: false})
      this.timeTextScrollListener = new r.ui.TimeTextScrollListener({
        el: this.el,
        timeText: this.timeText,
      })

      this.views = {}

      this.listenTo(this.model, {
        'add': this.onAdd,
        'remove': this.onRemove,
        'reset': this.onReset,
      })

      // replace traditional pagination with infinite scrolling
      $(window)
        .on('scroll.liveupdateListing', $.proxy(this, 'onScroll'))
      this.$el.siblings('nav.nextprev').remove()
    },

    onReset: function() {
      this.model.each(function(update) {
        var $updateEl = this.$el.find('.id-' + update.id)
        var view = new LiveUpdateView({
          el: $updateEl,
          model: update,
          permissions: this.permissions,
        })
        view.addEditButtonsIfAllowed()
        this.views[update.id] = view
      }, this)

      // fire a scroll event to see if we need to load another page because the
      // user has a very tall screen on a short first page.  we do this here
      // because we know we're safely bootstrapped at this point
      this.onScroll()

      this.timeTextScrollListener.start()
    },

    onAdd: function(update, listing, options) {
      var newView = new LiveUpdateView({
        model: update,
        permissions: this.permissions,
      })
      var newEl = newView.render().el

      this.timeText.refreshOne(newView.$('time.live-timestamp'))

      var newIndex = this.model.indexOf(update)
      var additions = [newEl]
      var separator
      if (options.at === 0) {
        var previousUpdate = this.model.at(newIndex + 1)
        separator = this.makeSeparator(previousUpdate, update)
        if (separator) {
          additions.push(separator)
        }
        this.$el.prepend(additions)
      } else if (options.at === undefined) {
        var nextUpdate = this.model.at(newIndex - 1)
        separator = this.makeSeparator(update, nextUpdate)
        if (separator) {
          additions.unshift(separator)
        }
        this.$el.append(additions)
      } else {
        r.error('wanted to insert update at arbitrary position')
        return
      }

      this.timeTextScrollListener.restart()

      this.views[update.id] = newView
    },

    makeSeparator: function(olderUpdate, newerUpdate) {
      var olderDate = parseTimestamp(olderUpdate.get('date'))
      var newerDate = parseTimestamp(newerUpdate.get('date'))
      var separatorDate
      var $el

      if (olderDate.hour() !== newerDate.hour()) {
        separatorDate = olderDate
          .minutes(0)
          .seconds(0)
          .milliseconds(0)

        $el = $($.parseHTML(r.templates.make('liveupdate/separator', {
          isoDate: separatorDate.toISOString(),
        })))
        this.timeText.refreshOne($el.find('time.live-timestamp'))
        return $el.get(0)
      }
    },

    onRemove: function(update) {
      // TODO: merge/delete orphaned separators
      this.views[update.id].remove()
      delete this.views[update.id]
    },

    onScroll: function() {
      if (this.fetchingMore && this.fetchingMore.state() === 'pending') {
        return
      }

      if (!this.model.hasMoreToFetch) {
        $(window).off('scroll.liveupdateListing')
        return
      }

      var bottomOfListing = this.$el.offset().top + this.$el.height()
      var topOfLastScreenful = bottomOfListing - window.innerHeight
      var nearBottom = ($(window).scrollTop() + 250 >= topOfLastScreenful)

      if (nearBottom) {
        this.fetchingMore = this.model.fetchMore()
        r.ui.showWorkingDeferred(this.$el, this.fetchingMore)
      }
    },
  })
}(r, Backbone, jQuery)
