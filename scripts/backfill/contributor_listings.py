from r2.models.query_cache import CachedQueryMutator

from reddit_liveupdate import models, queries


def backfill_listings():
    events = models.LiveUpdateEvent._all()

    with CachedQueryMutator() as m:
        for event in events:
            for contributor_id in event.contributors.iterkeys():
                m.insert(queries.get_contributor_events(contributor_id), [event])

            invites = models.LiveUpdateContributorInvitesByEvent.get_all(event)
            for invitee_id in invites.iterkeys():
                m.insert(queries.get_contributor_events(invitee_id), [event])


backfill_listings()
