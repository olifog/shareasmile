
function GetURLParameter(sParam) {
    var sPageURL = decodeURI(window.location.search.substring(1));
    var sURLVariables = sPageURL.split('&');
    for (var i = 0; i < sURLVariables.length; i++) {
        var sParameterName = sURLVariables[i].split('=');
        if (sParameterName[0] === sParam) {
            return sParameterName[1];
        }
    }
}

const name = GetURLParameter("name").replace(/\+/g,' ');
const product = GetURLParameter("product").replace(/\+/g,' ');

document.getElementById("details").innerHTML = "1x <b>" + product + "</b> for " + name;
