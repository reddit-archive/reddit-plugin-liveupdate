r.liveupdate.reporter = {
    init: function () {
        this.permissions = new r.liveupdate.PermissionSet(r.config.liveupdate_permissions)
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
            var $el = $(el)
            var author = $el.find('.author').data('name')

            if (this.permissions.allow('edit') || author == r.config.logged) {
                var $buttonRow = this.$buttonRow.clone()

                if ($el.thing().hasClass('stricken')) {
                    $buttonRow.find('button.strike').parent().remove()
                }

                $buttonRow.find('button').each(function (index, el) {
                    new r.ui.ConfirmButton({'el': el})
                })

                $el.append($buttonRow)
            }
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

r.liveupdate.PermissionSet = function (permissions) {
    this._permissions = permissions
}
r.liveupdate.PermissionSet.prototype = {
    isSuperUser: function () {
        return !!this._permissions.all
    },

    allow: function (name) {
        if (this.isSuperUser()) {
            return true
        }

        return !!this._permissions[name]
    }
}

$(function () { r.liveupdate.reporter.init() })
