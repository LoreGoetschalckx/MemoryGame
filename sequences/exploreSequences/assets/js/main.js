//------------------------------------------------------------------------------------------------------------------
/* GLOBAL */
let config = {};
const state = {
    workerIndex: 0,
    blockIndex: 0
};
let blockInfo = {};
let images = new Array();
const colors = {
    "target": "blue",
    "target repeat": "purple",
    "filler": "green",
    "vig": "red",
    "vig repeat": "orange"
};
const types = {
    "target": "target",
    "target repeat": "target repeat",
    "filler": "filler",
    "vig": "vigilance",
    "vig repeat": "vigilance repeat"
};

//------------------------------------------------------------------------------------------------------------------
/* HELPER FUNCTIONS */
function getAllIndexes(arr, val) {
    // from https://stackoverflow.com/questions/20798477/how-to-find-index-of-all-occurrences-of-element-in-array
    let indexes = [], i = -1;
    while ((i = arr.indexOf(val, i+1)) != -1){
        indexes.push(i);
    }
    return indexes;
}

function resetOpacity(){
    for (let i = 0; i < images.length; i++){
        images[i].style.opacity = 1;}
}

//------------------------------------------------------------------------------------------------------------------
/* SETTING UP PAGE ELEMENTS */
function setupButtons() {
    $("#PreviousWorker").click(decreaseWorkerIndex);
    $("#PreviousSequence").click(decreaseBlockIndex);
    $("#NextWorker").click(increaseWorkerIndex);
    $("#NextSequence").click(increaseBlockIndex);
}

function resetPage(){
    images = new Array();
    const information = document.getElementById("info");
    information.innerHTML = "";
    const myNode = document.getElementById("imageField");
    while (myNode.firstChild) {
        myNode.removeChild(myNode.firstChild);
    }
}

function arrangePage(numImages, imageSize, whiteSpace) {
    // after: https://stackoverflow.com/questions/11083345/creating-a-dynamic-grid-of-divs-with-javascript

    console.log(numImages);
    const w = window.innerWidth - (document.getElementById("sidenav").style.width + 400);
    const h = window.innerHeight;

    const numCols = Math.floor(w / (imageSize + 2 * whiteSpace));
    const numRows = Math.ceil(numImages / numCols);
    let e = document.getElementById("imageField");
    let count = 0;
    for (let r = 0; r < numRows; r++){
        const row = document.createElement("div");
        row.className = "line";
        row.id = "line_"+String(r);
        row.style.marginBottom = String(whiteSpace)+"px";
        row.style.marginTop = String(whiteSpace)+"px";
        row.style.clear = "both";
        row.style.display = "table";
        for (let c = 0; c < numCols; c++) {
            const cell = document.createElement("div");
            cell.className = "gridsquare";
            cell.style.width = String(100/numCols)+"%";
            cell.style.float = "left";
            const img = document.createElement("img");
            img.id = "image_" + String(count);
            img.className = "thumbnail";
            img.width = imageSize;
            img.height = imageSize;
            img.style.marginLeft = String(whiteSpace)+"px";
            img.style.marginRight = String(whiteSpace)+"px";
            img.style.marginTop = String(whiteSpace)+"px";
            img.style.marginBottom = String(whiteSpace)+"px";
            cell.appendChild(img);
            row.appendChild(cell);
            count = count + 1;
        }
        e.appendChild(row);
    }
    fillImages(state.blockIndex);
}

function fillImages(blockIndex){
    images = document.getElementsByClassName("thumbnail");
    for (let i = 0; i < images.length; i++){
        const path = blockInfo.sequences[blockIndex][i];
        images[i].src = config.baseUrl+path;
        images[i].style.outline = "solid";
        images[i].style.outlineColor = colors[blockInfo.types[blockIndex][i]];
        images[i].style.outlineWidth = "thick";
        images[i].ondblclick = makeOpenImageFunction(i);
        images[i].onclick = makeShowInfoFunction(i)};
}

//------------------------------------------------------------------------------------------------------------------
/* INTERACTIVITY */
function getBlockInfo(workerIndex) {
    let sequenceFile = config.sequenceDir + "//" + config.sequencePrefix + String(workerIndex).padStart(5, "0") + ".json";
    console.log(sequenceFile);

    $.getJSON(sequenceFile).done(function(data){
        blockInfo = data;
        resetPage();
        arrangePage(blockInfo.sequences[state.blockIndex].length,config.imageSize,config.whiteSpace);
    })
}

function makeOpenImageFunction(trialIndex){
    function openImage(){
    console.log(trialIndex);
    const path = blockInfo.sequences[state.blockIndex][trialIndex]
    const url = config.baseUrl + path;
    window.open(url);
    }
    return openImage;
}

function makeShowInfoFunction(trialIndex) {
    console.log("makeShowInfoFunction")
    function showInfo() {
        resetOpacity();
        const information = document.getElementById("info");
        information.innerHTML = "";
        let indices = getAllIndexes(blockInfo.sequences[state.blockIndex], blockInfo.sequences[state.blockIndex][trialIndex]);
        for (let i = 0; i < indices.length; i++) {
            images[indices[i]].style.opacity = 0.2;
            console.log("occurence ", i, " ", "trialIndex ", indices[i]);
            console.log("occurence ", i, " ", "file ", blockInfo.sequences[state.blockIndex][indices[i]]);
            console.log("occurence ", i, " ", "type ", types[blockInfo.types[state.blockIndex][indices[i]]]);

            information.innerHTML = information.innerHTML + "occurrence: "+String(i)+"<br>";
            information.innerHTML = information.innerHTML + "trialIndex: "+String(indices[i])+"<br>";
            information.innerHTML = information.innerHTML + "file: "+blockInfo.sequences[state.blockIndex][indices[i]]+"<br>";
            information.innerHTML = information.innerHTML + "type: "+types[blockInfo.types[state.blockIndex][indices[i]]]+"<br>";
            information.innerHTML = information.innerHTML + "<br>";
        }
    }
    return showInfo;
}

function decreaseWorkerIndex(){
    state.workerIndex = state.workerIndex -1;
    console.log("worker", state.workerIndex, "block",state.blockIndex);
    const information = document.getElementById("info");
    information.innerHTML = "";
    resetOpacity();
    $("#workerInfo").html("Worker: "+state.workerIndex);

    if (state.workerIndex == 0){
        $("#PreviousWorker").addClass("disabled");
    }
    else{
        console.log("disabling")
        $("#NextWorker").removeClass("disabled");
    }
    getBlockInfo(state.workerIndex);
}

function increaseWorkerIndex(){
    state.workerIndex = state.workerIndex +1;
    console.log("worker", state.workerIndex, "block",state.blockIndex);
    const information = document.getElementById("info");
    information.innerHTML = "";
    resetOpacity();
    $("#workerInfo").html("Worker: "+state.workerIndex);

    if (state.workerIndex == config.numWorkers -1){
        $("#NextWorker").addClass("disabled");
    }
    else{
        $("#PreviousWorker").removeClass("disabled");
    }
    getBlockInfo(state.workerIndex);
}

function increaseBlockIndex(){
    state.blockIndex = state.blockIndex +1;
    console.log("worker", state.workerIndex, "block",state.blockIndex);
    const information = document.getElementById("info");
    information.innerHTML = "";
    resetOpacity();
    $("#sequenceInfo").html("Sequence: "+state.blockIndex);

    if (state.blockIndex == blockInfo.sequences.length -1){
        $("#NextSequence").addClass("disabled");
    }
    else{

        $("#PreviousSequence").removeClass("disabled");
    }
    fillImages(state.blockIndex);
}

function decreaseBlockIndex(){
    state.blockIndex = state.blockIndex -1;
    console.log("worker", state.workerIndex, "block",state.blockIndex);
    const information = document.getElementById("info");
    information.innerHTML = "";
    resetOpacity();
    $("#sequenceInfo").html("Sequence: "+state.blockIndex);

    if (state.blockIndex == 0){
        $("#PreviousSequence").addClass("disabled");
    }
    else{
        $("#NextSequence").removeClass("disabled");
    }
    fillImages(state.blockIndex);
}

//------------------------------------------------------------------------------------------------------------------
/* MAIN */
$(document).ready(function() {
    $("#PreviousWorker").addClass("disabled");
    $("#PreviousSequence").addClass("disabled");
    $("#workerInfo").html("Worker: "+state.workerIndex);
    $("#sequenceInfo").html("Sequence: "+state.blockIndex);
    $.getJSON("exploreSequences/config.json").done(function(data) {
        config = data;
        $(window).resize(function() {
            resetPage();
            arrangePage(blockInfo.sequences[state.blockIndex].length,config.imageSize,config.whiteSpace);
        });
        getBlockInfo(state.workerIndex);
        setupButtons();
    });
});
