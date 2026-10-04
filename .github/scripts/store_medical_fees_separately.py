from pathlib import Path
import re

p=Path("index.html")
s=p.read_text(encoding="utf-8")

new_funcs=r'''  async function loadMedicalFeeDoctors(force=false){
    if(medicalFeeDoctorsLoaded&&!force){renderMedicalFeesTable();return;}
    try{
      const {data,error}=await db.rpc("get_medical_fee_usage");
      if(error)throw error;
      medicalFeeDoctors=(data||[]).map(row=>({
        userId:row.user_id,
        name:String(row.display_name||"Sans nom").trim()||"Sans nom",
        kits:num(row.kit_count),
        syringes:num(row.syringe_count),
        total:num(row.bank_amount)
      })).sort((a,b)=>a.name.localeCompare(b.name,"fr-FR",{sensitivity:"base"}));
      medicalFeeDoctorsLoaded=true;
      renderMedicalFeesTable();
    }catch(err){
      console.warn("Suivi des frais médicaux :",err);
      const body=$("medicalFeesBody");
      if(body)body.innerHTML='<tr><td colspan="5" class="empty">Impossible de charger le suivi des frais médicaux.</td></tr>';
    }
  }

  function renderMedicalFeesTable(){
    const body=$("medicalFeesBody");
    if(!body)return;
    const doctors=Array.isArray(medicalFeeDoctors)?medicalFeeDoctors:[];
    if(!doctors.length){
      body.innerHTML='<tr><td colspan="5" class="empty">Aucun docteur à afficher.</td></tr>';
      return;
    }
    body.innerHTML=doctors.map(row=>{
      const action=isAdmin?'<button class="btn danger medical-fees-reset" type="button" data-user-id="'+esc(row.userId||"")+'">Reset</button>':'<span class="muted">—</span>';
      return '<tr><td><strong style="color:#102845">'+esc(row.name)+'</strong></td><td>'+num(row.kits)+'</td><td>'+num(row.syringes)+'</td><td class="money">'+money(row.total)+'</td><td>'+action+'</td></tr>';
    }).join("");
  }

'''

pattern=r'  function medicalFeeResetMarker\(name\)\{.*?\n  function renderHistory\(\)\{'
m=re.search(pattern,s,re.S)
if not m:
    raise SystemExit("medical fee function block not found")
s=s[:m.start()]+new_funcs+'  function renderHistory(){'+s[m.end():]

old='''    const qDelta=type==="FRAIS_MEDICAUX"?0:(["ACHAT","DEPOT","CORRECTION_PLUS"].includes(type)?qty:removes?-qty:0);
    const cashDelta=type==="FRAIS_MEDICAUX"?0:(type==="ACHAT"?-total:type==="VENTE"?total:0);
    try{
      const {error}=await db.rpc("apply_movement",{p_resource_id:resource?.id||null,p_quantity_delta:qDelta,p_unit_price:["ACHAT","VENTE","FRAIS_MEDICAUX"].includes(type)?price:null,p_cash_delta:cashDelta,p_movement_type:type,p_note:note||null,p_effective_date:$("mvDate").value||todayISO()});
      if(error)throw error;
      $("movementForm").reset();$("mvDate").value=todayISO();fillMovementResources();await loadRemoteState();toast("Opération enregistrée en ligne.");
    }catch(err){dbError(err);}
'''
new='''    const qDelta=["ACHAT","DEPOT","CORRECTION_PLUS"].includes(type)?qty:removes?-qty:0;
    const cashDelta=type==="ACHAT"?-total:type==="VENTE"?total:0;
    try{
      if(medicalFees){
        const {error}=await db.rpc("add_medical_fee_usage",{p_resource_id:resource.id,p_quantity:qty});
        if(error)throw error;
        $("movementForm").reset();
        $("mvDate").value=todayISO();
        fillMovementResources();
        medicalFeeDoctorsLoaded=false;
        await loadMedicalFeeDoctors(true);
        toast("Frais médicaux ajoutés au tableau du docteur.");
        return;
      }
      const {error}=await db.rpc("apply_movement",{p_resource_id:resource?.id||null,p_quantity_delta:qDelta,p_unit_price:["ACHAT","VENTE"].includes(type)?price:null,p_cash_delta:cashDelta,p_movement_type:type,p_note:note||null,p_effective_date:$("mvDate").value||todayISO()});
      if(error)throw error;
      $("movementForm").reset();$("mvDate").value=todayISO();fillMovementResources();await loadRemoteState();toast("Opération enregistrée en ligne.");
    }catch(err){dbError(err);}
'''
if s.count(old)!=1:
    raise SystemExit(f"submit block count={s.count(old)}")
s=s.replace(old,new,1)

reset_pattern=r'''  \$\("medicalFeesBody"\)\?\.addEventListener\("click",async e=>\{.*?\n  \}\);\n  \$\("cashForm"\)\.addEventListener'''
m=re.search(reset_pattern,s,re.S)
if not m:
    raise SystemExit("reset listener block not found")
new_reset='''  $("medicalFeesBody")?.addEventListener("click",async e=>{
    const button=e.target.closest(".medical-fees-reset");
    if(!button)return;
    if(!isAdmin){toast("Action réservée à l’administrateur.");return;}
    const userId=button.dataset.userId||"";
    if(!userId)return;
    const row=medicalFeeDoctors.find(item=>String(item.userId)===String(userId));
    const doctor=row?.name||"ce docteur";
    try{
      button.disabled=true;
      const {error}=await db.rpc("admin_reset_medical_fee_usage",{p_user_id:userId});
      if(error)throw error;
      medicalFeeDoctorsLoaded=false;
      await loadMedicalFeeDoctors(true);
      toast("Compteur de "+doctor+" réinitialisé.");
    }catch(err){
      dbError(err,"Impossible de réinitialiser cette ligne.");
    }finally{
      button.disabled=false;
    }
  });
  $("cashForm").addEventListener'''
s=s[:m.start()]+new_reset+s[m.end():]

p.write_text(s,encoding="utf-8")
