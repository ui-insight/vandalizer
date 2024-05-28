//selecting all required elements
var file;
let attachArea = document.querySelector(".attach-area");
if (attachArea) {
  let dragText = attachArea.querySelector("header"),
  input = attachArea.querySelector("input");

  input.addEventListener("change", function(){
    file = this.files[0];
    attachArea.classList.add("active");
    showFile(); //calling function
  });

  //If user Drag File Over DropArea
  attachArea.addEventListener("dragover", (event)=>{
    event.preventDefault(); //preventing from default behaviour
    attachArea.classList.add("active");
    dragText.textContent = "Release to Upload File";
  });

  //If user leave dragged File from DropArea
  attachArea.addEventListener("dragleave", ()=>{
    console.log("leave");
    attachArea.classList.remove("active");
    dragText.textContent = "Drag & Drop to Upload File";
  });

  //If user drop File on DropArea
  attachArea.addEventListener("drop", (event)=>{
    event.preventDefault(); //preventing from default behaviour
    //getting user select file and [0] this means if user select multiple files then we'll select only the first one
    dragText.textContent = "Drag & Drop to Upload File";
    console.log("Looking for ifle");
    file = event.dataTransfer.files[0];
    console.log(file);
    showFile(); //calling function
  });
}

function showFile(){
  let fileType = file.type; //getting selected file type
  let validExtensions = ["application/pdf"]; //adding some valid image extensions in array
  if(validExtensions.includes(fileType)){ //if user selected file is an image file
    let fileReader = new FileReader(); //creating new FileReader object
    fileReader.onload = ()=>{
      let fileURL = fileReader.result; //passing user file source in fileURL variable
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
         url: "/read_pdf",
         data: JSON.stringify(model),
                      processData: false,
         contentType: "application/json",
         dataType: 'json',
         success: function(result) {
            console.log(result);

            $('#attachmentText').val(result.full_text)

         } 
       }); //adding that created img tag inside dropArea container
    }
    fileReader.readAsArrayBuffer(file);
  }else{
    alert("This is not a PDF!");
    attachArea.classList.remove("active");
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