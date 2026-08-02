// Run only if #map exists (to avoid errors on non-map pages)
if (document.getElementById('map') && !window.disableUniversalMap) {
  var map = L.map('map').setView([31.0461, 34.8516], 8);

  const layerName = window.selectedMapLayer || 'default';

  const providerUrls = {
    default: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    'OpenStreetMap.HOT': 'https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png',
    'Esri.WorldImagery': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    'Thunderforest.Transport': `https://tile.thunderforest.com/transport/{z}/{x}/{y}.png?apikey=${MAP_KEYS?.thunderforest || ''}`,
    'Thunderforest.OpenCycleMap': `https://tile.thunderforest.com/cycle/{z}/{x}/{y}.png?apikey=${MAP_KEYS?.thunderforest || ''}`,
    'Thunderforest.Outdoors': `https://tile.thunderforest.com/outdoors/{z}/{x}/{y}.png?apikey=${MAP_KEYS?.thunderforest || ''}`,
  };

  const providerAtt = {
    default:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | Maps by <a href="https://leafletjs.com/">Leaflet</a>',
    'OpenStreetMap.HOT':
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, ' +
      'Tiles style by <a href="https://www.hotosm.org/">Humanitarian OpenStreetMap Team</a> | Maps by <a href="https://leafletjs.com/">Leaflet</a>',
    'Esri.WorldImagery':
      'Tiles &copy; <a href="https://www.esri.com/">Esri</a> — Source: Esri, i-cubed, USDA, USGS, AEX, ' +
      'GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community | Maps by <a href="https://leafletjs.com/">Leaflet</a>',
    'Thunderforest.Transport':
      '&copy; <a href="https://www.thunderforest.com/">Thunderforest</a>, ' +
      'Data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> | Maps by <a href="https://leafletjs.com/">Leaflet</a>',
    'Thunderforest.OpenCycleMap':
      '&copy; <a href="https://www.thunderforest.com/">Thunderforest</a>, ' +
      'Data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> | Maps by <a href="https://leafletjs.com/">Leaflet</a>',
    'Thunderforest.Outdoors':
      '&copy; <a href="https://www.thunderforest.com/">Thunderforest</a>, ' +
      'Data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> | Maps by <a href="https://leafletjs.com/">Leaflet</a>',
  };

  L.tileLayer(providerUrls[layerName], {
    attribution: providerAtt[layerName],
    maxZoom: 19,
  }).addTo(map);

  let allGeoJsonLayer = null;
  let cachedGeoJsonData = null;

  function getStarDisplay(avg) {
    let fullStars = Math.round(avg);
    let starsHtml = '';
    for (let i = 1; i <= 5; i++) {
      starsHtml += `<span style="color:${i <= fullStars ? 'gold' : 'gray'};">&#9733;</span>`;
    }
    return starsHtml;
  }

  function initReviewStars(markerId) {
    const container = document.querySelector(`.rating-stars[data-marker="${markerId}"]`);
    if (!container) return;

    const stars = container.querySelectorAll('.review-star');

    container.addEventListener('mouseover', function (e) {
      if (e.target.classList.contains('review-star')) {
        const hoverVal = parseInt(e.target.dataset.value);
        stars.forEach((star) => {
          const val = parseInt(star.dataset.value);
          star.classList.toggle('gold', val <= hoverVal);
        });
      }
    });

    container.addEventListener('mouseout', function () {
      const selected = parseInt(container.getAttribute('data-selected') || '0');
      stars.forEach((star) => {
        const val = parseInt(star.dataset.value);
        star.classList.toggle('gold', val <= selected);
      });
    });

    stars.forEach((star) => {
      star.addEventListener('click', function () {
        const value = parseInt(this.dataset.value);
        container.setAttribute('data-selected', value);
        stars.forEach((s) => {
          const val = parseInt(s.dataset.value);
          s.classList.toggle('gold', val <= value);
        });
      });
    });
  }

  // Delete lingering <br> or spaces for text divs in loadMarkers
  document.addEventListener('input', function (e) {
    if (e.target.classList.contains('review-editable')) {
      if (e.target.innerText.trim() === '') {
        e.target.innerHTML = '';
      }
    }
  });

  function limitReviewText(el, markerId) {
    const maxChars = 500;
    const text = el.innerText;

    if (text.length > maxChars) {
      el.innerText = text.substring(0, maxChars);

      // Move cursor to the end after truncation
      const range = document.createRange();
      const sel = window.getSelection();
      range.selectNodeContents(el);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    }

    const remaining = maxChars - el.innerText.length;
    const charCountEl = document.getElementById(`charCount-${markerId}`);
    if (charCountEl) {
      charCountEl.textContent = `${remaining} characters remaining`;
    }
  }

  function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength).trim() + '...';
  }

  function loadMarkers() {
    fetch('/map/geojson-features')
      .then(response => response.json())
      .then(data => {
        cachedGeoJsonData = data; 
        renderFilteredMarkers();  
      });
  }

  function renderFilteredMarkers() {
    if (!cachedGeoJsonData) return;

    if (allGeoJsonLayer && map.hasLayer(allGeoJsonLayer)) {
      map.removeLayer(allGeoJsonLayer);
    }

    const selectedCliqueIds = getSelectedCliqueIds();

    allGeoJsonLayer = L.geoJSON(cachedGeoJsonData, {
      filter: (feature) => selectedCliqueIds.includes(feature.properties.clique_id),
      pointToLayer: function (feature, latlng) {
        const desc = feature.properties.description;
        const cliqueName = feature.properties.clique_name;
        const markerId = feature.properties.marker_id;
        const avg = feature.properties.average_review.toFixed(1);
        const total = feature.properties.total_reviews;
        const userReview = feature.properties.user_review;
        const otherReviews = feature.properties.reviews;
        const userEvents = feature.properties.user_events;
        const otherEvents = feature.properties.events;
        const stars = getStarDisplay(avg);
        const color = feature.properties.clique_color;
        const markerIcon = feature.properties.icon;
        const cliqueId = feature.properties.clique_id;

        let popupContent = `
          <div style="font-family: 'Poppins', sans-serif;">
            <strong>${desc} <span style="color: gray; font-weight: normal;">(${cliqueName})</span></strong><br>
            <div style="margin: 5px 0;">⚖️ Average Rating: ${stars} (${avg} / 5 from ${total} reviews)</div>
        `;

        if (userReview) {
          const userStars = getStarDisplay(userReview.stars);
          const userComment = userReview.commentary ? `"${truncateText(userReview.commentary, 40)}"` : '';
          popupContent += `
            <hr>
            <div style="color: gray;">
              <strong>Your Review:</strong><br>
              Stars: ${userStars}<br>
              ${userComment}
            </div>
            <a href="/map/edit-review/${markerId}">
              <button class="btn btn-info-small" style="margin-top:5px;">Edit Review</button>
            </a>
          `;
        } else {
          popupContent += `
            <label>Leave a review:</label><br>
            <div class="rating-stars" data-marker="${markerId}" data-selected="0" style="padding-bottom: 5px">
              ${[1, 2, 3, 4, 5].map((i) => `<span class="review-star" data-value="${i}">&#9733;</span>`).join('')}
            </div>
            <div id="review-comment-${markerId}" class="review-editable" contenteditable="true"
                oninput="limitReviewText(this, ${markerId})"
                placeholder="Your review (optional)"
                style="border: 1px solid #ccc; padding: 6px; min-height: 60px;"></div>
            <div id="charCount-${markerId}" style="font-size: 0.85em; color: grey;">500 characters remaining</div>
            <br>
            <button onclick="submitReview(${markerId})" class="btn btn-primary" style="padding: 4px 10px; font-size: 14px;">
              Submit Review
            </button>
          `;
        }

        if (otherReviews.length > 0) {
          popupContent += `
            <hr>
            <div><strong>📝 Other Reviews:</strong></div><div style="max-height: 140px; overflow-y: auto;">
              <ul style="padding-left: 18px; margin-top:5px;">
          `;
          otherReviews.forEach((r) => {
            popupContent += `
              <li style="display: flex; align-items: flex-start; padding-top: 8px; word-break: break-word;">
              ${
                r.user_pic !== 'default.jpg'
                  ? `<img src="/static/assets/avatars_profile_pics/${r.user_pic}"
                          alt="User"
                          style="width: 32px; height: 32px; border-radius: 50%; object-fit: cover; margin-right: 10px;">`
                  : `<i class="bi bi-person-circle"
                          style="font-size: 2rem; color: #888; margin-right: 10px;"></i>`
              }
                <div>
                  ${getStarDisplay(r.stars)}
                  ${r.commentary ? `"${r.commentary}"` : ''}
                  <em>(${r.user})</em>
                </div>
              </li>`;
          });
          popupContent += `
              </ul>
            </div>
          `;
        }

        // check if any event is between today and 3 days from now (inclusive)
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const endDate = new Date(today);
        endDate.setDate(today.getDate() + 3);
        const allEvents = userEvents.concat(otherEvents);

        // Parse from "YYYY-MM-DD" format to Date object
        function parseDate(dateStr) {
          const [year, month, day] = dateStr.split('-').map(Number);
          return new Date(year, month - 1, day); // Month is 0-indexed
        }

        const hasEventInRange = allEvents.some((ev) => {
          const eventDate = parseDate(ev.date);
          return eventDate >= today && eventDate <= endDate;
        });

        const allEventsSorted = userEvents
          .concat(otherEvents)
          .map((e) => ({
            ...e,
            dateObj: new Date(e.date),
          }))
          .sort((a, b) => a.dateObj - b.dateObj);

        if (allEventsSorted.length > 0) {
          popupContent += `
            <hr>
            <div><strong>🗓️ Events:</strong></div><div style="color: blue; max-height: 100px; overflow-y: auto;">
              <ul style="margin-top: 5px; list-style: none; padding: 0;">
          `;

          allEventsSorted.forEach((e) => {
            const isOwnEvent = e.is_own_event; // Assume passing a flag for user's own events
            const eventOwnerText = isOwnEvent ? `<strong>Your</strong> event on` : e.user ? `<strong>${e.user}</strong>'s event on` : 'Event on';

            popupContent += `
                <li style="text-align: center; margin-top: 5px; word-break: break-word;">
                  ${eventOwnerText} <strong>${e.date}</strong> at <strong>${e.time}</strong><br>
                  ${e.description}
                </li>
              `;
          });

          popupContent += `
              </ul>
            </div>
          `;
        }

        popupContent += `
          <div style="display: flex; justify-content: center; margin-top: 8px;">
            <a class="btn btn-info-small" style="margin-right: 8px;" href="/event/add/${markerId}/${cliqueId}">Add Event</a>
            <a class="btn btn-info-small" href="/event/edit-events/${markerId}/${cliqueId}">Edit Events</a>
          </div>
        `;

        popupContent += `</div>`;

        const iconSize = 40;

        if (userEvents == 0 && otherEvents == 0) {
          // Standard black marker (No events)
          var customIcon = L.divIcon({
            className: 'custom-div-icon',
            html: `<div class='marker-pin' style='background:${color}; width:${iconSize}px; height:${iconSize}px;'>
                    <i class='bi ${markerIcon}' style='font-size:${iconSize * 0.6}px;'></i>
                  </div>`,
            iconSize: [iconSize, iconSize],
            iconAnchor: [iconSize / 2, iconSize],
          });
        } else if (hasEventInRange) {
          // Pulsing blue marker (Event occurring within 3 days)
          var customIcon = L.divIcon({
            className: 'custom-div-icon-event',
            html: `<div class='marker-pin' style='background:${color}; width:${iconSize}px; height:${iconSize}px;'>
                    <i class='bi ${markerIcon}' style='font-size:${iconSize * 0.6}px;'></i>
                  </div>`,
            iconSize: [iconSize, iconSize],
            iconAnchor: [iconSize / 2, iconSize],
          });
        } else {
          var customIcon = L.divIcon({
            // Static blue marker (Future events beyond 3 days)
            className: 'custom-div-icon',
            html: `<div class='marker-pin' style='color: #0a0ef8; background:${color}; width:${iconSize}px; height:${iconSize}px;'>
                    <i class='bi ${markerIcon}' style='font-size:${iconSize * 0.6}px;'></i>
                  </div>`,
            iconSize: [iconSize, iconSize],
            iconAnchor: [iconSize / 2, iconSize],
          });
        }

        const marker = L.marker(latlng, { icon: customIcon }).bindPopup(popupContent);
        marker.on('popupopen', () => initReviewStars(markerId));
        return marker;
      },
    }).addTo(map);
  }

  function getSelectedCliqueIds() {
    const checkboxes = document.querySelectorAll('.clique-checkbox');
    return Array.from(checkboxes)
      .filter((cb) => cb.checked)
      .map((cb) => parseInt(cb.value));
  }

  function submitReview(markerId) {
    const container = document.querySelector(`.rating-stars[data-marker="${markerId}"]`);
    const selected = parseInt(container.getAttribute('data-selected') || '0');
    const commentary = document.getElementById(`review-comment-${markerId}`).innerText.trim();

    if (selected === 0) {
      alert('Please provide a star rating.');
      return;
    }

    fetch(`/map/rate-marker/${markerId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating: selected, commentary: commentary }),
    })
      .then((res) => res.json())
      .then((data) => {
        alert(data.message);
        if (data.success) {
          map.closePopup();
          map.eachLayer((layer) => {
            if (layer instanceof L.Marker && layer.getPopup()) {
              layer.remove();
            }
          });
          loadMarkers();
        }
      });
  }

  function discardMarker() {
    if (window.tempMarker) {
      map.removeLayer(window.tempMarker);
      map.closePopup();
    }
  }

  function saveMarker(lat, lng, uniqueId) {
    const title = document.getElementById(`${uniqueId}-title`).value.trim();
    const rating = document.getElementById(`${uniqueId}-rating`).value;
    const cliqueId = document.getElementById(`${uniqueId}-clique`).value;
    const commentary = document.getElementById(`${uniqueId}-commentary`).innerText.trim();

    if (!title || !rating || !cliqueId) {
      alert('The fields title, rating, and clique are required.');
      return;
    }

    fetch('/map/add-marker', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        latitude: lat,
        longitude: lng,
        title: title,
        rating: rating,
        clique_id: cliqueId,
        commentary: commentary,
      }),
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.success) {
          alert('Marker added successfully!');
          map.closePopup();
          map.eachLayer((layer) => {
            if (layer instanceof L.Marker && layer.getPopup()) {
              layer.remove();
            }
          });
          loadMarkers();
        } else {
          alert('Error: ' + data.message);
        }
      })
      .catch((error) => console.error('Error saving marker:', error));
  }

  map.on('click', function (e) {
    const lat = e.latlng.lat;
    const lng = e.latlng.lng;

    const uniqueId = `popup-${Date.now()}-${Math.floor(Math.random() * 1000)}`;

    const popupContent = `
      <div style="font-family: 'Poppins', sans-serif;">
        <input type="text" id="${uniqueId}-title" class="form-control" placeholder="Title" required><br>

        <label>Rate this location:</label><br>
        <div id="${uniqueId}-rating-stars">
          ${[1, 2, 3, 4, 5].map((i) => `<span class="star" data-value="${i}">&#9733;</span>`).join('')}
        </div>
        <input type="hidden" id="${uniqueId}-rating"><br>

        <label>Your Review:</label><br>
        <div id="${uniqueId}-commentary" class="review-editable" contenteditable="true" placeholder="Your review (optional)"></div><br>

        <label for="${uniqueId}-clique">Select Clique:</label><br>
        <select id="${uniqueId}-clique" class="form-control" size="3" required>
          ${window.currentUserCliques.map((clique) => `<option value="${clique.id}">${clique.name}</option>`).join('')}
        </select><br>

        <button onclick="saveMarker(${lat}, ${lng}, '${uniqueId}')" class="btn btn-primary-small">Save</button>
        <button onclick="discardMarker()" class="btn btn-secondary">Discard</button>
        <a href="/clique/create-clique" class="btn btn-info-small">Create New Clique</a>
      </div>
    `;

    const tempMarker = L.marker([lat, lng]).addTo(map).bindPopup(popupContent).openPopup();
    window.tempMarker = tempMarker;

    tempMarker.on('popupclose', function () {
      if (window.tempMarker) {
        map.removeLayer(window.tempMarker);
      }
    });

    setTimeout(() => {
      const stars = document.querySelectorAll(`#${uniqueId}-rating-stars .star`);
      stars.forEach((star) => {
        star.addEventListener('mouseover', () => {
          const val = parseInt(star.dataset.value);
          stars.forEach((s) => {
            s.classList.toggle('gold', parseInt(s.dataset.value) <= val);
          });
        });

        star.addEventListener('mouseout', () => {
          const selected = parseInt(document.getElementById(`${uniqueId}-rating`).value || '0');
          stars.forEach((s) => {
            s.classList.toggle('gold', parseInt(s.dataset.value) <= selected);
          });
        });

        star.addEventListener('click', () => {
          const selected = parseInt(star.dataset.value);
          document.getElementById(`${uniqueId}-rating`).value = selected;
          stars.forEach((s) => {
            s.classList.toggle('gold', parseInt(s.dataset.value) <= selected);
          });
        });
      });
    }, 0);
  });

  window.addEventListener('DOMContentLoaded', () => {
    const filterBox = document.getElementById('clique-filter-box');
    const filterButton = document.getElementById('filter-button');

    if (filterButton && filterBox) {
      filterButton.addEventListener('click', () => {
        filterBox.classList.toggle('show');
      });
    }

    document.querySelectorAll('.clique-checkbox').forEach((cb) => {
      const saved = localStorage.getItem(`clique-${cb.value}`);
      if (saved !== null) {
        cb.checked = saved === 'true';
      }

      cb.addEventListener('change', () => {
        localStorage.setItem(`clique-${cb.value}`, cb.checked);
        renderFilteredMarkers();
      });
    });

    const selectAllBtn = document.getElementById('select-all');
    if (selectAllBtn) {
      selectAllBtn.addEventListener('click', () => {
        document.querySelectorAll('.clique-checkbox').forEach((cb) => {
          cb.checked = true;
          localStorage.setItem(`clique-${cb.value}`, 'true');
        });
        renderFilteredMarkers();
      });
    }

    const clearAllBtn = document.getElementById('clear-all');
    if (clearAllBtn) {
      clearAllBtn.addEventListener('click', () => {
        document.querySelectorAll('.clique-checkbox').forEach((cb) => {
          cb.checked = false;
          localStorage.setItem(`clique-${cb.value}`, 'false');
        });
        renderFilteredMarkers();
      });
    }

    loadMarkers();
  });
}
