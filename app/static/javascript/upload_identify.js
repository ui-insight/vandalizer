//selecting all required elements
const dropArea = document.querySelector(".drag-area"),
dragText = dropArea.querySelector("header"),
//button = dropArea.querySelector("button"),
input = dropArea.querySelector("input"),
dragArea = document.querySelector(".drop-area");
let file; //this is a global variable and we'll use it inside multiple functions
//button.onclick = ()=>{
//  input.click(); //if user click on the button then the input also clicked
//}
input.addEventListener("change", function(){
  //getting user select file and [0] this means if user select multiple files then we'll select only the first one
  file = this.files[0];
  dropArea.classList.add("active");
  showFile(); //calling function
});

//If user Drag File Over DropArea
dropArea.addEventListener("dragover", (event)=>{
  event.preventDefault(); //preventing from default behaviour
  dropArea.classList.add("active");
  dragText.textContent = "Release to Upload File";
});

//If user leave dragged File from DropArea
dropArea.addEventListener("dragleave", ()=>{
  console.log("leave");
  dropArea.classList.remove("active");
  dragText.textContent = "Drag & Drop to Upload File";
});

//If user drop File on DropArea
dropArea.addEventListener("drop", (event)=>{
  event.preventDefault(); //preventing from default behaviour
  //getting user select file and [0] this means if user select multiple files then we'll select only the first one
  dragText.textContent = "Drag & Drop to Upload File";
  file = event.dataTransfer.files[0];
  showFile(); //calling function
});

$('#loading-area')
    .hide()  // Hide it initially
    .ajaxStart(function() {
        $(this).show();
    })
    // .ajaxStop(function() {
    //     $(this).hide();
    // })
;

function showFile(){
  let fileType = file.type; //getting selected file type
  let validExtensions = ["application/pdf"]; //adding some valid image extensions in array
  if(validExtensions.includes(fileType)){ //if user selected file is an image file
    let fileReader = new FileReader(); //creating new FileReader object
    fileReader.onload = ()=>{
      let fileURL = fileReader.result; //passing user file source in fileURL variable
        // UNCOMMENT THIS BELOW LINE. I GOT AN ERROR WHILE UPLOADING THIS POST SO I COMMENTED IT
      //let imgTag = `<img id="image" src="/static/images/images.jpeg" alt="image">`; //creating an img tag and passing user selected file source inside src attribute
      //dropArea.innerHTML = imgTag;
      $('#loading-area').show();
      $('#drag-area').hide();
       var filetype = file.type;
          var filename = file.name;
      var base64String = getB64Str(fileURL);

      var model = {
          contentType: filetype,
          contentAsBase64String: base64String,
          fileName: filename,
          space: $('#current-space-id')[0].innerHTML
      };

      $.ajax({
         type: "POST",
         url: "/upload",
         data: JSON.stringify(model),
                      processData: false,
         contentType: "application/json",
         dataType: 'json',
         success: function(result) {
          $('#loading-area').hide();
          $('#drag-area').show();
          let newRow = $("<tr>");
          let newCell = $("<td>");
          let newLink = $("<a>").attr("href", "/review/" + result.uuid).text(filename);
            
          newCell.append(newLink);
          newRow.append(newCell);
            
          $("#doc-body").append(newRow);

         } 
       }); //adding that created img tag inside dropArea container
    }
    fileReader.readAsArrayBuffer(file);
  }else{
    alert("This is not a PDF!");
    dropArea.classList.remove("active");
    dragText.textContent = "Drag & Drop to Upload File";
  }
}

function getB64Str(buffer) {
          var binary = '';
          var bytes = new Uint8Array(buffer);
          var len = bytes.byteLength;
          for (var i = 0; i < len; i++) {
              binary += String.fromCharCode(bytes[i]);
          }
          return window.btoa(binary);
}