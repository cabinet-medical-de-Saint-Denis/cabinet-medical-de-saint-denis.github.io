create or replace function public.queue_recipe_missing_with_suppliers(
  p_recipe_id uuid,
  p_quantity numeric,
  p_supplier_choices jsonb default '{}'::jsonb
)
returns numeric
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_item record;
  v_stock numeric;
  v_outstanding numeric;
  v_total_required numeric;
  v_missing numeric;
  v_total_added numeric := 0;
  v_found boolean := false;
  v_supplier_count integer;
  v_supplier_id uuid;
  v_choice text;
begin
  if auth.uid() is null or not private.is_approved() then raise exception 'Accès non autorisé'; end if;
  if p_quantity is null or p_quantity <= 0 or p_quantity <> trunc(p_quantity) then raise exception 'Quantité de fabrication invalide'; end if;
  if not exists (select 1 from public.recipes r where r.id=p_recipe_id and r.active=true) then raise exception 'Recette introuvable'; end if;

  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('fabrication-plans',0));

  insert into public.fabrication_plans(recipe_id,quantity,updated_by,updated_at)
  values(p_recipe_id,p_quantity,auth.uid(),now())
  on conflict(recipe_id) do update
  set quantity=excluded.quantity,updated_by=excluded.updated_by,updated_at=excluded.updated_at;

  for v_item in
    select ri.ingredient_resource_id as resource_id
    from public.recipe_ingredients ri
    join public.resources res on res.id=ri.ingredient_resource_id and res.active=true and res.category='ingredient'
    where ri.recipe_id=p_recipe_id and ri.quantity>0
    order by ri.ingredient_resource_id
  loop
    v_found:=true;
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(v_item.resource_id::text,0));

    select coalesce(r.stock,0) into v_stock
    from public.resources r where r.id=v_item.resource_id for update;

    select coalesce(sum(ri.quantity*fp.quantity),0) into v_total_required
    from public.fabrication_plans fp
    join public.recipe_ingredients ri on ri.recipe_id=fp.recipe_id
    where ri.ingredient_resource_id=v_item.resource_id and fp.quantity>0;

    select coalesce(sum(o.quantity),0) into v_outstanding
    from public.orders o
    where o.resource_id=v_item.resource_id and o.status in ('a_commander','en_cours');

    v_missing:=greatest(v_total_required-v_stock-v_outstanding,0);

    if v_missing>0 then
      v_supplier_id:=null;
      select count(*) into v_supplier_count
      from public.suppliers s where s.resource_id=v_item.resource_id and s.active=true;

      if v_supplier_count=0 then raise exception 'Aucun fournisseur actif pour un ingrédient requis'; end if;

      v_choice:=p_supplier_choices->>v_item.resource_id::text;
      if nullif(v_choice,'') is not null then
        begin
          v_supplier_id:=v_choice::uuid;
        exception when invalid_text_representation then
          raise exception 'Choix de fournisseur invalide';
        end;

        if not exists(
          select 1 from public.suppliers s
          where s.id=v_supplier_id and s.resource_id=v_item.resource_id and s.active=true
        ) then raise exception 'Fournisseur invalide pour un ingrédient requis'; end if;
      elsif v_supplier_count>1 then
        raise exception 'Choisissez un fournisseur pour chaque ingrédient proposé par plusieurs fournisseurs';
      else
        select s.id into v_supplier_id
        from public.suppliers s
        where s.resource_id=v_item.resource_id and s.active=true
        order by s.created_at nulls last,s.id
        limit 1;
      end if;

      perform public.queue_order_with_supplier(v_item.resource_id,v_supplier_id,v_missing);
      v_total_added:=v_total_added+v_missing;
    end if;
  end loop;

  if not v_found then raise exception 'Cette recette ne contient aucun ingrédient'; end if;
  return v_total_added;
end;
$function$;

create or replace function public.apply_movement(
  p_resource_id uuid,p_quantity_delta numeric,p_unit_price numeric,p_cash_delta numeric,
  p_movement_type text,p_note text default null,p_effective_date date default current_date
)
returns uuid
language plpgsql
security definer
set search_path to 'public'
as $function$
declare v_id uuid; v_stock numeric;
begin
  if auth.uid() is null or not (select private.is_approved()) then raise exception 'Accès non autorisé'; end if;

  if p_movement_type='RETRAIT_STOCK' then
    if p_quantity_delta is null or p_quantity_delta>=0 or p_quantity_delta<>trunc(p_quantity_delta) then raise exception 'Indiquez une quantité entière à retirer'; end if;
    if coalesce(p_cash_delta,0)<>0 or p_unit_price is not null then raise exception 'Un retrait de stock ne doit comporter aucun mouvement d’argent'; end if;
    if not exists(
      select 1 from public.resources r join public.recipes rc on rc.product_resource_id=r.id
      where r.id=p_resource_id and r.active=true and rc.active=true
    ) then raise exception 'Le retrait est réservé aux articles des recettes'; end if;
  end if;

  if p_resource_id is not null then
    select stock into v_stock from public.resources where id=p_resource_id for update;
    if not found then raise exception 'Ressource introuvable'; end if;
    if v_stock+coalesce(p_quantity_delta,0)<0 then raise exception 'Stock insuffisant'; end if;

    update public.resources
    set stock=stock+coalesce(p_quantity_delta,0),
        unit_price=case
          when p_movement_type='ACHAT' and p_unit_price is not null and p_unit_price>=0 then p_unit_price
          else unit_price
        end
    where id=p_resource_id;
  end if;

  update public.cabinet_state set cash_balance=cash_balance+coalesce(p_cash_delta,0) where id=1;

  insert into public.movements(movement_type,resource_id,quantity_delta,unit_price,cash_delta,note,created_by,effective_date)
  values(coalesce(nullif(trim(p_movement_type),''),'ajustement'),p_resource_id,coalesce(p_quantity_delta,0),p_unit_price,coalesce(p_cash_delta,0),p_note,auth.uid(),coalesce(p_effective_date,current_date))
  returning id into v_id;

  return v_id;
end;
$function$;

create or replace function public.set_pharmacy_quantity(p_product_resource_id uuid,p_quantity numeric)
returns boolean
language plpgsql
security definer
set search_path to ''
as $function$
declare v_stock numeric; v_sellable boolean;
begin
  if auth.uid() is null or not private.is_approved() then raise exception 'Accès non autorisé'; end if;
  if p_quantity is null or p_quantity<0 then raise exception 'Quantité invalide'; end if;

  select coalesce(r.stock,0),
         coalesce(p.pharmacy_sellable,case when upper(r.name) in ('KIT DE SOIN','SERINGUE VIVIFIANTE') then false else true end)
  into v_stock,v_sellable
  from public.recipes rc
  join public.resources r on r.id=rc.product_resource_id
  left join public.recipe_pricing p on p.product_resource_id=r.id
  where rc.product_resource_id=p_product_resource_id and rc.active=true
  for update of r;

  if not found then raise exception 'Recette introuvable'; end if;
  if not v_sellable then raise exception 'Cette recette n’est pas vendue à la pharmacie'; end if;
  if p_quantity>v_stock then raise exception 'La quantité en pharmacie ne peut pas dépasser le stock disponible (%).',v_stock; end if;

  insert into public.pharmacy_stock(product_resource_id,quantity,updated_at,updated_by)
  values(p_product_resource_id,p_quantity,now(),auth.uid())
  on conflict(product_resource_id) do update
  set quantity=excluded.quantity,updated_at=now(),updated_by=auth.uid();

  return true;
end;
$function$;

create or replace function public.record_pharmacy_count(p_product_resource_id uuid,p_current_quantity numeric)
returns table(sold_quantity numeric,revenue numeric,new_quantity numeric)
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_stored numeric; v_price numeric; v_sellable boolean; v_name text;
  v_sold numeric; v_revenue numeric; v_stock numeric;
begin
  if auth.uid() is null or not private.is_approved() then raise exception 'Accès non autorisé'; end if;
  if p_current_quantity is null or p_current_quantity<0 then raise exception 'Quantité actuelle invalide'; end if;

  select r.name,
         case when coalesce(p.pharmacy_sellable,case when upper(r.name) in ('KIT DE SOIN','SERINGUE VIVIFIANTE') then false else true end)
              then coalesce(p.pharmacy_price,r.unit_price,0) else null end,
         coalesce(p.pharmacy_sellable,case when upper(r.name) in ('KIT DE SOIN','SERINGUE VIVIFIANTE') then false else true end)
  into v_name,v_price,v_sellable
  from public.recipes rc
  join public.resources r on r.id=rc.product_resource_id
  left join public.recipe_pricing p on p.product_resource_id=r.id
  where rc.product_resource_id=p_product_resource_id and rc.active=true;

  if not found then raise exception 'Recette introuvable'; end if;
  if not v_sellable then raise exception 'Cette recette n’est pas vendue à la pharmacie'; end if;

  insert into public.pharmacy_stock(product_resource_id,quantity,updated_at,updated_by)
  values(p_product_resource_id,0,now(),auth.uid())
  on conflict(product_resource_id) do nothing;

  select s.quantity into v_stored
  from public.pharmacy_stock s
  where s.product_resource_id=p_product_resource_id
  for update;

  if p_current_quantity>v_stored then
    raise exception 'La quantité actuelle dépasse la quantité enregistrée. Utilisez la case Quantité en pharmacie pour le réapprovisionnement.';
  end if;

  v_sold:=v_stored-p_current_quantity;

  select coalesce(r.stock,0) into v_stock
  from public.resources r
  where r.id=p_product_resource_id
  for update;

  if not found then raise exception 'Produit introuvable dans le stock'; end if;
  if v_sold>v_stock then raise exception 'Vente impossible : % unité(s) vendue(s) mais seulement % en stock.',v_sold,v_stock; end if;

  v_revenue:=v_sold*coalesce(v_price,0);

  update public.pharmacy_stock
  set quantity=p_current_quantity,updated_at=now(),updated_by=auth.uid()
  where product_resource_id=p_product_resource_id;

  if v_sold>0 then
    update public.resources set stock=stock-v_sold where id=p_product_resource_id;
    update public.cabinet_state set cash_balance=cash_balance+v_revenue where id=1;

    insert into public.movements(movement_type,resource_id,quantity_delta,unit_price,cash_delta,note,created_by,effective_date)
    values('PHARMACIE_VENTE',p_product_resource_id,-v_sold,v_price,v_revenue,'Vente enregistrée depuis la pharmacie',auth.uid(),current_date);
  end if;

  return query select v_sold,v_revenue,p_current_quantity;
end;
$function$;
