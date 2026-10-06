-- Restreindre les opérations Achat et Vente selon le grade RP, sans modifier les autres opérations.
CREATE OR REPLACE FUNCTION public.apply_movement(p_resource_id uuid, p_quantity_delta numeric, p_unit_price numeric, p_cash_delta numeric, p_movement_type text, p_note text DEFAULT NULL::text, p_effective_date date DEFAULT CURRENT_DATE)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare
  v_id uuid;
  v_stock numeric;
begin
  if auth.uid() is null or not (select private.is_approved()) then
    raise exception 'Accès non autorisé';
  end if;

  -- Les achats et ventes saisis ici sont réservés aux grades de direction.
  if upper(btrim(coalesce(p_movement_type, ''))) in ('ACHAT', 'VENTE')
     and not exists (
       select 1 from public.profiles p
       where p.id = (select auth.uid())
         and p.access_status = 'approved'
         and p.medical_grade in ('chef_de_cabinet', 'medecin_adjoint')
     ) then
    raise exception 'Les achats et ventes sont réservés au chef de cabinet et au médecin adjoint'
      using errcode = '42501';
  end if;

  if p_movement_type = 'RETRAIT_STOCK' then
    if p_quantity_delta is null or p_quantity_delta >= 0 or p_quantity_delta <> trunc(p_quantity_delta) then
      raise exception 'Indiquez une quantité entière à retirer';
    end if;
    if coalesce(p_cash_delta,0) <> 0 or p_unit_price is not null then
      raise exception 'Un retrait de stock ne doit comporter aucun mouvement d’argent';
    end if;
    if not exists (
      select 1
      from public.resources r
      join public.recipes rc on rc.product_resource_id = r.id
      where r.id = p_resource_id and r.active = true and rc.active = true
    ) then
      raise exception 'Le retrait est réservé aux articles des recettes';
    end if;
  end if;

  if p_resource_id is not null then
    select stock into v_stock
    from public.resources
    where id = p_resource_id
    for update;

    if not found then
      raise exception 'Ressource introuvable';
    end if;

    if v_stock + coalesce(p_quantity_delta,0) < 0 then
      raise exception 'Stock insuffisant';
    end if;

    update public.resources
    set stock = stock + coalesce(p_quantity_delta,0),
        unit_price = case
          when p_movement_type = 'ACHAT'
           and p_unit_price is not null
           and p_unit_price >= 0
          then p_unit_price
          else unit_price
        end
    where id = p_resource_id;
  end if;

  update public.cabinet_state
  set cash_balance = cash_balance + coalesce(p_cash_delta,0)
  where id = 1;

  insert into public.movements(
    movement_type, resource_id, quantity_delta, unit_price, cash_delta,
    note, created_by, effective_date
  )
  values (
    coalesce(nullif(trim(p_movement_type),''),'ajustement'),
    p_resource_id,
    coalesce(p_quantity_delta,0),
    p_unit_price,
    coalesce(p_cash_delta,0),
    p_note,
    auth.uid(),
    coalesce(p_effective_date,current_date)
  )
  returning id into v_id;

  return v_id;
end;
$function$;
