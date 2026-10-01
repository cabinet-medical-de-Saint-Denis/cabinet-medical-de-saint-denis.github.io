update public.recipes
set output_quantity = 1
where active = true and coalesce(output_quantity, 1) <> 1;

create or replace function public.craft_recipe(p_recipe_id uuid, p_quantity numeric)
returns uuid
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_product_id uuid;
  v_recipe_name text;
  v_batch_id uuid := gen_random_uuid();
  ing record;
  v_needed numeric;
  v_current numeric;
  v_after numeric;
begin
  if auth.uid() is null or not private.is_approved() then
    raise exception 'Accès non autorisé';
  end if;

  if p_quantity is null or p_quantity <= 0 or p_quantity <> trunc(p_quantity) then
    raise exception 'Quantité invalide';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('fabrication-plans', 0));

  select product_resource_id, name
  into v_product_id, v_recipe_name
  from public.recipes
  where id = p_recipe_id and active = true;

  if not found then
    raise exception 'Recette introuvable';
  end if;

  if exists (
    select 1 from public.recipe_ingredients ri
    where ri.recipe_id = p_recipe_id
      and ri.ingredient_resource_id = v_product_id
  ) then
    raise exception 'Recette invalide : le produit fabriqué ne peut pas être utilisé comme ingrédient';
  end if;

  for ing in
    select ri.ingredient_resource_id, ri.quantity, r.name
    from public.recipe_ingredients ri
    join public.resources r
      on r.id = ri.ingredient_resource_id
     and r.active = true
     and r.category = 'ingredient'
    where ri.recipe_id = p_recipe_id and ri.quantity > 0
    order by r.name
  loop
    v_needed := ing.quantity * p_quantity;
    select coalesce(stock,0) into v_current
    from public.resources
    where id = ing.ingredient_resource_id
    for update;

    if v_current < v_needed then
      raise exception 'Stock insuffisant pour % : besoin %, stock %', ing.name, v_needed, v_current;
    end if;
  end loop;

  if not exists (
    select 1
    from public.recipe_ingredients ri
    join public.resources r
      on r.id = ri.ingredient_resource_id
     and r.active = true
     and r.category = 'ingredient'
    where ri.recipe_id = p_recipe_id and ri.quantity > 0
  ) then
    raise exception 'Cette recette ne contient aucun ingrédient valide';
  end if;

  for ing in
    select ri.ingredient_resource_id, ri.quantity, r.name
    from public.recipe_ingredients ri
    join public.resources r
      on r.id = ri.ingredient_resource_id
     and r.active = true
     and r.category = 'ingredient'
    where ri.recipe_id = p_recipe_id and ri.quantity > 0
    order by r.name
  loop
    v_needed := ing.quantity * p_quantity;

    select coalesce(stock,0) into v_current
    from public.resources
    where id = ing.ingredient_resource_id
    for update;

    update public.resources
    set stock = stock - v_needed
    where id = ing.ingredient_resource_id and stock >= v_needed
    returning stock into v_after;

    if not found or v_after <> v_current - v_needed then
      raise exception 'Erreur de déduction du stock pour %', ing.name;
    end if;

    insert into public.movements(
      movement_type, resource_id, quantity_delta, cash_delta, note, details,
      created_by, effective_date
    )
    values (
      'CONSOMMATION_FAB', ing.ingredient_resource_id, -v_needed, 0,
      'Pour ' || p_quantity || ' × ' || v_recipe_name,
      jsonb_build_object('batch_id', v_batch_id, 'recipe_id', p_recipe_id, 'craft_quantity', p_quantity),
      auth.uid(), current_date
    );
  end loop;

  update public.resources
  set stock = stock + p_quantity
  where id = v_product_id;

  insert into public.movements(
    id, movement_type, resource_id, quantity_delta, cash_delta, note, details,
    created_by, effective_date
  )
  values (
    v_batch_id, 'FABRICATION', v_product_id, p_quantity, 0,
    'Fabrication terminée',
    jsonb_build_object('recipe_id', p_recipe_id, 'craft_quantity', p_quantity),
    auth.uid(), current_date
  );

  update public.fabrication_plans
  set quantity = greatest(quantity - p_quantity, 0),
      updated_by = auth.uid(),
      updated_at = now()
  where recipe_id = p_recipe_id;

  delete from public.fabrication_plans
  where recipe_id = p_recipe_id and quantity <= 0;

  return v_batch_id;
end;
$function$;
