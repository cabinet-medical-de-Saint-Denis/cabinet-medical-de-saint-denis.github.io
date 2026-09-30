-- Chaque utilisateur réorganise uniquement les rapports de son propre carnet.
-- La mise à jour de tout le sous-intercalaire est atomique ; les contenus restent intacts.
create or replace function public.reorder_personal_consultation_reports(p_report_ids uuid[])
returns table(report_id uuid, report_sort_order integer)
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  v_owner uuid := auth.uid();
  v_category uuid;
  v_subcategory text;
  v_count integer := cardinality(p_report_ids);
  v_total integer;
  v_selected integer;
begin
  if v_owner is null then
    raise exception 'Authentification requise.' using errcode = '42501';
  end if;
  if v_count is null or v_count = 0
     or exists (select 1 from unnest(p_report_ids) as item(id) where item.id is null)
     or (select count(distinct item.id) from unnest(p_report_ids) as item(id)) <> v_count then
    raise exception 'La liste des rapports est invalide.' using errcode = '22023';
  end if;

  -- Sérialise les réorganisations du même carnet, sans verrouiller les autres utilisateurs.
  perform pg_advisory_xact_lock(hashtextextended(v_owner::text || ':consultation-report-order', 0));

  select t.category_id, coalesce(t.subcategory, '')
    into v_category, v_subcategory
    from public.consultation_user_templates as t
    where t.id = p_report_ids[array_lower(p_report_ids, 1)]
      and t.owner_id = v_owner and t.active = true;
  if not found then
    raise exception 'Rapport indisponible dans ton carnet.' using errcode = '42501';
  end if;

  perform t.id from public.consultation_user_templates as t
    where t.owner_id = v_owner and t.active = true
      and t.category_id = v_category and coalesce(t.subcategory, '') = v_subcategory
    order by t.id for update;

  select count(*), count(*) filter (where t.id = any(p_report_ids))
    into v_total, v_selected
    from public.consultation_user_templates as t
    where t.owner_id = v_owner and t.active = true
      and t.category_id = v_category and coalesce(t.subcategory, '') = v_subcategory;
  if v_total <> v_count or v_selected <> v_count then
    raise exception 'La liste des rapports a changé. Actualise le carnet avant de réessayer.' using errcode = '22023';
  end if;

  return query
    update public.consultation_user_templates as t
      set sort_order = (ordered.position * 10)::integer,
          updated_at = now()
      from unnest(p_report_ids) with ordinality as ordered(id, position)
      where t.id = ordered.id and t.owner_id = v_owner
      returning t.id, t.sort_order;
end;
$function$;

revoke all on function public.reorder_personal_consultation_reports(uuid[]) from public, anon;
grant execute on function public.reorder_personal_consultation_reports(uuid[]) to authenticated;
