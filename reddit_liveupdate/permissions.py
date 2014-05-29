from pylons.i18n import N_

from r2.lib.permissions import PermissionSet


class ContributorPermissionSet(PermissionSet):
    info = {
        "update": {
            "title": N_("update"),
            "description": N_("post updates"),
        },

        "manage": {
            "title": N_("manage contributors"),
            "description": N_("add, remove, and change permissions of contributors"),
        },

        "settings": {
            "title": N_("settings"),
            "description": N_("change the title and description"),
        },

        "edit": {
            "title": N_("edit"),
            "description": N_("strike and delete others' updates"),
        },

        "close": {
            "title": N_("close stream"),
            "description": N_("permanently close the stream"),
        },
    }

    def allow(self, permission):
        if self.is_superuser():
            return True
        return self.get(permission, False)

    def without(self, permission):
        if self.is_superuser():
            permissions = {k: True for k in self.info}
        else:
            permissions = self.copy()

        permissions.pop(permission, None)
        return ContributorPermissionSet(permissions)


ContributorPermissionSet.SUPERUSER = ContributorPermissionSet.loads("+all")
ContributorPermissionSet.NONE = ContributorPermissionSet.loads("")
