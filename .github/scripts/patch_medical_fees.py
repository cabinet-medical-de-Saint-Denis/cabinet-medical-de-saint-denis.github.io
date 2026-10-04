from pathlib import Path
import re

path=Path("index.html")
s=path.read_text(encoding="utf-8")
original=s

def once(old,new,label):
    global s
    c=s.count(old)
    if c!=1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {c}")
    s=s.replace(old,new,1)

def sub_once(pattern,repl,label,flags=re.S):
    global s
    s2,n=re.subn(pattern,lambda _m: repl,s,count=1,flags=flags)
    if n!=1:
        raise SystemExit(f"{label}: expected 1 regex match, found {n}")
    s=s2

once(
    '                    <option value="RETRAIT_STOCK">Retrait du stock</option>\n',
    '                    <option value="RETRAIT_STOCK">Retrait du stock</option>\n                    <option value="FRAIS_MEDICAUX">Frais médicaux</option>\n',
    "operation option"
)

movement_end='''            </form>
          </div>
        </div>
      </div>
    </section>


    <section id="debts" class="view">'''
movement_new='''            </form>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top:18px">
        <h3 class="section-title">Frais médicaux par docteur <small>suivi des consommables utilisés en service</small></h3>
        <div class="card-body">
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Docteur</th>
                  <th>KIT DE SOIN utilisés</th>
                  <th>SERINGUE VIVIFIANTE utilisées</th>
                  <th>À reverser à la banque</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody id="medicalFeesBody">
                <tr><td colspan="5" class="empty">Chargement du suivi médical…</td></tr>
              </tbody>
            </table>
          </div>
          <p class="hint" style="margin:12px 0 0">Le montant correspond au coût de fabrication des KIT DE SOIN et SERINGUE VIVIFIANTE utilisés. Il n’est pas ajouté à la comptabilité du cabinet.</p>
        </div>
      </div>
    </section>


    <section id="debts" class="view">'''
once(movement_end,movement_new,"medical fees table")

once(
    '  let pharmacyLoading = false;\n',
    '  let pharmacyLoading = false;\n  let medicalFeeDoctors=[];\n  let medicalFeeDoctorsLoaded=false;\n',
    "medical fee globals"
)

m=re.search(r'function typeLabel\(([^)]*)\)\{',s)
if not m:
    raise SystemExit("typeLabel function not found")
s=s[:m.end()]+'\n    if(arguments[0]==="FRAIS_MEDICAUX")return "Frais médicaux";\n    if(arguments[0]==="FRAIS_MEDICAUX_RESET")return "Reset frais médicaux";'+s[m.end():]

new_fill='''  function normalizedMedicalResourceName(value){
    return resourceNameText(value).normalize("NFD").replace(/[\\u0300-\\u036f]/g,"");
  }
  function isMedicalFeeResource(resource){
    const name=normalizedMedicalResourceName(resource?.name||"");
    return name==="KIT DE SOIN" || name==="SERINGUE VIVIFIANTE";
  }
  function fillMovementResources(){
    const current=$("mvResource").value;
    const type=$("mvType").value;
    const withdrawal=type==="RETRAIT_STOCK";
    const medicalFees=type==="FRAIS_MEDICAUX";
    let resources=activeResources().filter(r=>r.kind==="ingredient" || state.recipes.some(rc=>rc.productId===r.id));
    if(withdrawal)resources=resources.filter(r=>state.recipes.some(rc=>rc.productId===r.id));
    if(medicalFees)resources=resources.filter(r=>state.recipes.some(rc=>rc.productId===r.id)&&isMedicalFeeResource(r));
    $("mvResource").innerHTML=resources.map(r=>'<option value="'+esc(r.id)+'">'+esc(resourceNameText(r.name))+'</option>').join("")+
      (withdrawal||medicalFees?"":'<option value="__OTHER__">Autre (indiquer le motif dans la note ci-dessous)</option>');
    if(resources.some(r=>r.id===current)||(!withdrawal&&!medicalFees&&current==="__OTHER__"))$("mvResource").value=current;
    const integerQty=withdrawal||medicalFees;
    $("mvQty").min=integerQty?"1":"0.01";
    $("mvQty").step=integerQty?"1":"0.01";
    $("mvPrice").disabled=integerQty;
    $("mvPrice").closest(".field").style.display=integerQty?"none":"";
    $("mvTotal").closest(".field").querySelector("label").textContent="Total";
    syncMovementPrice();
  }
'''
sub_once(r'  function fillMovementResources\(\)\{.*?\n  function recipeUnitCost\(',new_fill+'  function recipeUnitCost(',"fill movement block")

new_sync='''  function syncMovementPrice(){
    const type=$("mvType").value;
    const withdrawal=type==="RETRAIT_STOCK";
    const medicalFees=type==="FRAIS_MEDICAUX";
    const r=res($("mvResource").value);
    $("mvPrice").value=withdrawal?"0.00":medicalFees?recipeUnitCost(r?.id).toFixed(2):num(r?.unitPrice).toFixed(2);
    const bankNote="à remettre à la banque du cabinet";
    const medicalNote="frais médicaux · à remettre à la banque du cabinet";
    if(withdrawal){
      $("mvNote").value=bankNote;
      $("mvNote").readOnly=true;
    }else if(medicalFees){
      $("mvNote").value=medicalNote;
      $("mvNote").readOnly=true;
    }else{
      if($("mvNote").value===bankNote||$("mvNote").value===medicalNote)$("mvNote").value="";
      $("mvNote").readOnly=false;
    }
    calcMovementTotal();
  }
  function calcMovementTotal(){
    const type=$("mvType").value;
    const qty=num($("mvQty").value);
    const unitCost=(type==="RETRAIT_STOCK"||type==="FRAIS_MEDICAUX")?recipeUnitCost($("mvResource").value):num($("mvPrice").value);
    $("mvTotal").value=money(qty*unitCost);
  }
'''
sub_once(r'  function syncMovementPrice\(\)\{.*?\n  function outstandingOrderQty\(',new_sync+'  function outstandingOrderQty(',"movement price block")

helpers='''  function medicalFeeResetMarker(name){
    return "__MEDICAL_FEES_RESET__:"+encodeURIComponent(String(name||"").trim());
  }
  function medicalFeeDoctorNamesFromHistory(){
    const names=new Set();
    state.history.forEach(h=>{
      if(h.type==="FRAIS_MEDICAUX" && h.actorName)names.add(String(h.actorName).trim());
    });
    if(currentProfile?.display_name)names.add(String(currentProfile.display_name).trim());
    return [...names].filter(Boolean);
  }
  async function loadMedicalFeeDoctors(force=false){
    if(medicalFeeDoctorsLoaded&&!force){renderMedicalFeesTable();return;}
    const names=new Set(medicalFeeDoctorNamesFromHistory());
    if(isAdmin){
      try{
        const {data,error}=await db.rpc("admin_list_profiles");
        if(error)throw error;
        (data||[]).filter(u=>u.access_status==="approved").forEach(u=>{
          if(u.display_name)names.add(String(u.display_name).trim());
        });
      }catch(err){console.warn("Liste des docteurs pour frais médicaux :",err);}
    }
    medicalFeeDoctors=[...names].filter(Boolean).sort((a,b)=>a.localeCompare(b,"fr-FR",{sensitivity:"base"}));
    medicalFeeDoctorsLoaded=true;
    renderMedicalFeesTable();
  }
  function medicalFeeSummaryForDoctor(name){
    const marker=medicalFeeResetMarker(name);
    let start=-1;
    state.history.forEach((h,index)=>{
      if(h.type==="FRAIS_MEDICAUX_RESET" && h.note===marker)start=index;
    });
    let kits=0,syringes=0,total=0;
    state.history.slice(start+1).forEach(h=>{
      if(h.type!=="FRAIS_MEDICAUX" || String(h.actorName||"").trim()!==name)return;
      const resource=h.resourceId?res(h.resourceId):null;
      const resourceName=normalizedMedicalResourceName(resource?.name||h.resourceName||"");
      const qty=Math.abs(num(h.qty));
      if(resourceName==="KIT DE SOIN")kits+=qty;
      if(resourceName==="SERINGUE VIVIFIANTE")syringes+=qty;
      total+=h.total!=null?Math.abs(num(h.total)):qty*Math.abs(num(h.unitPrice));
    });
    return {kits,syringes,total};
  }
  function renderMedicalFeesTable(){
    const body=$("medicalFeesBody");
    if(!body)return;
    const names=new Set([...medicalFeeDoctors,...medicalFeeDoctorNamesFromHistory()]);
    const doctors=[...names].filter(Boolean).sort((a,b)=>a.localeCompare(b,"fr-FR",{sensitivity:"base"}));
    if(!doctors.length){
      body.innerHTML='<tr><td colspan="5" class="empty">Aucun docteur à afficher.</td></tr>';
      return;
    }
    body.innerHTML=doctors.map(name=>{
      const summary=medicalFeeSummaryForDoctor(name);
      const action=isAdmin?'<button class="btn danger medical-fees-reset" type="button" data-doctor="'+encodeURIComponent(name)+'">Reset</button>':'<span class="muted">—</span>';
      return '<tr><td><strong style="color:#102845">'+esc(name)+'</strong></td><td>'+summary.kits+'</td><td>'+summary.syringes+'</td><td class="money">'+money(summary.total)+'</td><td>'+action+'</td></tr>';
    }).join("");
  }
'''
once('  function renderHistory(){',helpers+'  function renderHistory(){',"tracking helpers")

once(
    '        const isStockWithdrawal=h.movement_type==="RETRAIT_STOCK";\n        const withdrawalUnitCost=isStockWithdrawal?recipeUnitCost(h.resource_id):null;\n',
    '        const isStockWithdrawal=h.movement_type==="RETRAIT_STOCK";\n        const isMedicalFees=h.movement_type==="FRAIS_MEDICAUX";\n        const withdrawalUnitCost=isStockWithdrawal?recipeUnitCost(h.resource_id):null;\n',
    "history medical flag"
)

once(
    '  function renderAll(){loadNavigation();renderDashboard();renderInventory();fillMovementResources();renderCraft();renderRecipes();fillRemoveIngredientSelect();renderSuppliers();renderHistory();renderSettings();}',
    '  function renderAll(){loadNavigation();renderDashboard();renderInventory();fillMovementResources();renderCraft();renderRecipes();fillRemoveIngredientSelect();renderSuppliers();renderHistory();renderMedicalFeesTable();loadMedicalFeeDoctors();renderSettings();}',
    "render all integration"
)

sub_once(
    r'    const type=\$\("mvType"\)\.value,qty=num\(\$\("mvQty"\)\.value\),price=num\(\$\("mvPrice"\)\.value\),total=qty\*price;\n    const note=type==="RETRAIT_STOCK"\?"à remettre à la banque du cabinet":\$\("mvNote"\)\.value\.trim\(\);',
    '    const type=$("mvType").value,qty=num($("mvQty").value);\n    const medicalFees=type==="FRAIS_MEDICAUX";\n    const price=medicalFees?recipeUnitCost(resource?.id):num($("mvPrice").value),total=qty*price;\n    const note=type==="RETRAIT_STOCK"?"à remettre à la banque du cabinet":medicalFees?"frais médicaux · à remettre à la banque du cabinet":$("mvNote").value.trim();',
    "submit values",
    flags=0
)

once(
    '    if(type==="RETRAIT_STOCK"&&(!resource||!state.recipes.some(rc=>rc.productId===resource.id)||!Number.isInteger(qty))){\n      toast("Choisis un article de recette et une quantité entière.");return;\n    }\n    const removes=["SORTIE","VENTE","CORRECTION_MOINS","RETRAIT_STOCK"].includes(type);',
    '    if(type==="RETRAIT_STOCK"&&(!resource||!state.recipes.some(rc=>rc.productId===resource.id)||!Number.isInteger(qty))){\n      toast("Choisis un article de recette et une quantité entière.");return;\n    }\n    if(medicalFees&&(!resource||!isMedicalFeeResource(resource)||!state.recipes.some(rc=>rc.productId===resource.id)||!Number.isInteger(qty))){\n      toast("Les frais médicaux acceptent uniquement KIT DE SOIN ou SERINGUE VIVIFIANTE avec une quantité entière.");return;\n    }\n    const removes=["SORTIE","VENTE","CORRECTION_MOINS","RETRAIT_STOCK","FRAIS_MEDICAUX"].includes(type);',
    "medical validation"
)

once(
    'p_unit_price:["ACHAT","VENTE"].includes(type)?price:null,p_cash_delta:cashDelta',
    'p_unit_price:["ACHAT","VENTE","FRAIS_MEDICAUX"].includes(type)?price:null,p_cash_delta:cashDelta',
    "cost snapshot"
)

reset_anchor='  $("resetMovement").addEventListener("click",()=>{$("movementForm").reset();$("mvDate").value=todayISO();fillMovementResources();calcMovementTotal();toast("Zone de saisie réinitialisée.");});\n'
reset_code=reset_anchor+'''  $("medicalFeesBody")?.addEventListener("click",async e=>{
    const button=e.target.closest(".medical-fees-reset");
    if(!button)return;
    if(!isAdmin){toast("Action réservée à l’administrateur.");return;}
    const doctor=decodeURIComponent(button.dataset.doctor||"");
    if(!doctor)return;
    try{
      button.disabled=true;
      const {error}=await db.rpc("apply_movement",{
        p_resource_id:null,
        p_quantity_delta:0,
        p_unit_price:null,
        p_cash_delta:0,
        p_movement_type:"FRAIS_MEDICAUX_RESET",
        p_note:medicalFeeResetMarker(doctor),
        p_effective_date:todayISO()
      });
      if(error)throw error;
      medicalFeeDoctorsLoaded=false;
      await loadRemoteState(true,true);
      await loadMedicalFeeDoctors(true);
      toast("Compteur de "+doctor+" réinitialisé.");
    }catch(err){
      dbError(err,"Impossible de réinitialiser cette ligne.");
    }finally{
      button.disabled=false;
    }
  });
'''
once(reset_anchor,reset_code,"reset handler")

if s==original:
    raise SystemExit("No changes made")
path.write_text(s,encoding="utf-8")
