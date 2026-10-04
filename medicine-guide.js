(function(){
  const STATIC_PAGE_COUNT=64;
  const staticPages=Array.from({length:STATIC_PAGE_COUNT},(_,i)=>({
    kind:"image", number:i+1, src:"https://cabinet-medical-de-rhodes.github.io/assets/guide-medecine/"+(i+1)+".webp"
  }));

  function init(ctx){
    const {db,$,toast,dbError,getCurrentUser,getCurrentProfile}=ctx;
    let customPages=[],pageIndex=0,busy=false;

    const isChief=()=>{
      const u=getCurrentUser(),p=getCurrentProfile();
      return !!u && p?.access_status==="approved" && p?.medical_grade==="chef_de_cabinet";
    };

    const finalPage={kind:"final",title:"MERCI A LILITH, LA SOUVERAINE",body:"MERCI A LILITH, LA SOUVERAINE"};
    const allPages=()=>[...staticPages,...customPages.map(p=>({kind:"custom",...p})),finalPage];

    function render(){
      const pages=allPages();
      pageIndex=Math.max(0,Math.min(pageIndex,pages.length-1));
      const page=pages[pageIndex];
      const imageWrap=$("guideImagePage"), image=$("guidePageImage"), paper=$("guidePaper");

      if(page.kind==="image"){
        imageWrap.hidden=false;
        paper.hidden=true;
        image.src=page.src;
        image.alt="Guide de la médecine — page "+page.number;
        image.onerror=()=>{ $("guideStatus").textContent="Image introuvable : page "+page.number; };
      }else{
        imageWrap.hidden=true;
        paper.hidden=false;
        $("guidePageTitle").textContent=page.title||"Guide de la médecine";
        $("guidePageBody").textContent=page.body||"";
        $("guidePageBody").classList.toggle("guide-final",page.kind==="final");
      }

      $("guidePrev").disabled=pageIndex<=0;
      $("guideNext").disabled=pageIndex>=pages.length-1;
      $("guideCounter").textContent="Page "+(pageIndex+1)+" / "+pages.length;
      $("guideDeletePage").disabled=page.kind!=="custom"||!isChief();
    }

    async function load(){
      if(busy)return;
      busy=true;
      $("guideStatus").textContent="Chargement…";
      try{
        const {data,error}=await db.from("medicine_guide_pages")
          .select("*")
          .eq("is_final",false)
          .order("sort_order",{ascending:true})
          .order("created_at",{ascending:true});
        if(error)throw error;
        customPages=data||[];
        $("guideToggleAdmin").hidden=!isChief();
        $("guideStatus").textContent="64 pages originales";
        render();
      }catch(e){
        customPages=[];
        $("guideToggleAdmin").hidden=!isChief();
        $("guideStatus").textContent="64 pages originales";
        render();
        console.warn("Guide custom pages unavailable",e);
      }finally{busy=false;}
    }

    $("guideHome").addEventListener("click",()=>{pageIndex=0;render();});
    $("guideRefresh").addEventListener("click",load);
    $("guidePrev").addEventListener("click",()=>{if(pageIndex>0){pageIndex--;render();}});
    $("guideNext").addEventListener("click",()=>{if(pageIndex<allPages().length-1){pageIndex++;render();}});
    $("guideToggleAdmin").addEventListener("click",()=>{if(isChief())$("guideAdmin").classList.toggle("show");});

    $("guideAddPage").addEventListener("click",async()=>{
      if(!isChief())return toast("Action réservée au Chef de cabinet.");
      const title=$("guideNewTitle").value.trim(),body=$("guideNewBody").value.trim();
      if(!title||!body)return toast("Renseigne le titre et le contenu.");
      const order=1000+customPages.length+1;
      const {error}=await db.from("medicine_guide_pages").insert({title,body,sort_order:order,is_final:false});
      if(error)return dbError(error);
      $("guideNewTitle").value="";
      $("guideNewBody").value="";
      await load();
      pageIndex=STATIC_PAGE_COUNT+customPages.length-1;
      render();
      toast("Page ajoutée.");
    });

    $("guideDeletePage").addEventListener("click",async()=>{
      if(!isChief())return toast("Action réservée au Chef de cabinet.");
      const page=allPages()[pageIndex];
      if(!page||page.kind!=="custom")return toast("Les 64 pages originales du guide ne sont pas supprimables depuis le site.");
      if(!confirm("Supprimer cette page du Guide de la médecine ?"))return;
      const {error}=await db.from("medicine_guide_pages").delete().eq("id",page.id);
      if(error)return dbError(error);
      await load();
      pageIndex=Math.min(pageIndex,allPages().length-1);
      render();
      toast("Page supprimée.");
    });

    render();
    return {load,render,isChief};
  }

  window.RhodesMedicineGuide={init};
})();