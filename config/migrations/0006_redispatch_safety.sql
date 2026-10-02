-- Redispatch safety: a dispatch's end only rules out a late effect for effect classes
-- that can prove it, and absence counts toward a retry only when it was observed after
-- landing was ruled out. See docs/execution/dispatch-safety.md.

-- "quiesced" overstated what acquiring the lock proves; it is renamed to what it is.
alter table ari_execution_dispatch_fences rename column quiesced_at to lock_released_at;
update ari_execution_dispatch_fences set state = 'lock_released' where state = 'quiesced';

-- Effect class recorded at reservation. Legacy fences stay null and are treated as
-- unbounded: nothing about their end rules out a late effect.
alter table ari_execution_dispatch_fences add column effect_terminality text;

-- Identity of the lock file the dispatcher actually held while crossing. A later
-- proof must lock this same inode; a replaced or missing file proves nothing.
alter table ari_execution_dispatch_fences add column lock_path text;
alter table ari_execution_dispatch_fences add column lock_device integer;
alter table ari_execution_dispatch_fences add column lock_inode integer;

-- Issued exactly once, when ARI establishes that this dispatch can no longer land.
-- An absence reconciliation must present it to count toward redispatch.
alter table ari_execution_dispatch_fences add column landing_token text;
alter table ari_execution_dispatch_fences add column landing_ruled_out_at text;

-- A fence that never crossed can never land.
update ari_execution_dispatch_fences
set landing_token = 'landing-' || lower(hex(randomblob(16))),
    landing_ruled_out_at = revoked_at
where state = 'revoked';

-- retry_eligible was derived from absence plus a fence state observed at any time.
-- It is replaced by redispatch_safe, which no legacy record can claim: none was bound
-- to an observation made after landing was ruled out.
alter table ari_execution_effect_reconciliations rename column retry_eligible to redispatch_safe;
update ari_execution_effect_reconciliations set redispatch_safe = 0;
alter table ari_execution_effect_reconciliations add column landing_token text;

create unique index if not exists idx_execution_dispatch_fences_landing_token
    on ari_execution_dispatch_fences(landing_token);
