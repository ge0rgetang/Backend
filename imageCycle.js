
//Declare an image array same as calling new Array();
var img = []
img[0] = "/static/img/launch.PNG";
img[1] = "/static/img/pond.PNG";
img[2] = "/static/img/anon.PNG";
img[3] = "/static/img/poolList.PNG";
img[4] = "/static/img/pool.PNG";
img[5] = "/static/img/chapter.PNG";
img[6] = "/static/img/friends.PNG";
img[7] = "/static/img/chat.PNG";

//Select all elements on the page with the name attribute equal to screenImage
var images = document.querySelectorAll('[name=screenImage]');

//For each image bind the click event
for(var i=0; i < images.length; i++)
{
  var image = images[i];
  //https://developer.mozilla.org/en-US/docs/Web/API/EventTarget.addEventListener
  image.addEventListener('click', imageClicked(), false);
}

function imageClicked()
{
  //Use a closure to wrap the counter variable
  //so each image element has their own unique counter
  var counter = img.length-1;
  return function(event)
  {
    //Increment counter
    counter++;
    //The context of "this" is the image element
    //Use a modulus
    this.src = img[counter % img.length];
  }
}
