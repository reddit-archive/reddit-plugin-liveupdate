r.liveupdate.editor = {
    init: function () {
        this.$listing = $('.liveupdate-listing')
        this.$buttonRow = $(r.templates.make('liveupdate/edit-buttons', {
            strikeLabel: r._('strike'),
            deleteLabel: r._('delete')
        }))

        this.$listing
            .on('confirm', '.strike', $.proxy(this, 'strike'))
            .on('confirm', '.delete', $.proxy(this, 'delete_'))
            .on('more-updates', $.proxy(this, 'onMoreUpdates'))

        this._addButtons(this.$listing.find('tr.thing td'))
    },

    onMoreUpdates: function (ev, updates) {
        this._addButtons(updates.filter('tr.thing').find('td'))
    },

    _addButtons: function (updates) {
        updates.each($.proxy(function (index, el) {
            var $buttonRow = this.$buttonRow.clone()
            var $el = $(el)

            if ($el.thing().hasClass('stricken')) {
                $buttonRow.find('button.strike').parent().remove()
            }

            $buttonRow.find('button').each(function (index, el) {
                new r.ui.ConfirmButton({'el': el})
            })

            $el.append($buttonRow)
        }, this))
    },

    strike: function (ev) {
        var $update = $(ev.target).thing()
        var $button = $update.find('.strike.confirm-button')

        $button.text(r._('striking...'))

        $.ajax({
            'type': 'POST',
            'dataType': 'json',
            'url': '/api/live/' + r.config.liveupdate_event + '/strike_update',
            'data': {
                'id': $update.thing_id(),
                'uh': r.config.modhash
            }
        }).done(function () {
            $update.addClass('stricken')
            $button.text(r._('stricken'))
        })
    },

    delete_: function (ev) {
        var $update = $(ev.target).thing()
        var $button = $update.find('.delete.confirm-button')

        $button.text(r._('deleting...'))

        $.ajax({
            'type': 'POST',
            'dataType': 'json',
            'url': '/api/live/' + r.config.liveupdate_event + '/delete_update',
            'data': {
                'id': $update.thing_id(),
                'uh': r.config.modhash
            }
        }).done(function () {
            $button.text(r._('deleted'))
            $update.fadeOut(function () {
                $(this).remove()
            })
        })
    }
}

$.insert_liveupdates = function (things, append) {
    var $listing = $('.liveupdate-listing'),
        $initial = $listing.find('tr.initial')

    _.each(things, function (thing) {
        var $newThing = $($.unsafe(thing.data.content))
        r.liveupdate.editor._addButtons($newThing.find('td'))
        $initial.after($newThing)
    })
}

$(function () { r.liveupdate.editor.init() })
