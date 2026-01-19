// Scale fix for responsive images
(function() {
  var images = document.querySelectorAll('img');
  for (var i = 0; i < images.length; i++) {
    var img = images[i];
    img.style.maxWidth = '100%';
    img.style.height = 'auto';
  }
})();