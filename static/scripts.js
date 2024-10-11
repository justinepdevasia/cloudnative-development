document.addEventListener('DOMContentLoaded', function() {
    const fileUpload = document.getElementById('file-upload');
    const fileName = document.getElementById('file-name');
    const uploadForm = document.getElementById('upload-form');
    const progressBar = document.getElementById('progress-bar');
    const progress = progressBar.querySelector('.progress');
    const gallery = document.getElementById('gallery');
    const modal = document.getElementById('imageModal');
    const modalImage = document.getElementById('modalImage');
    const modalCaption = document.getElementById('modalCaption');
    const modalDescription = document.getElementById('modalDescription');
    const closeBtn = modal.querySelector('.close');

    fileUpload.addEventListener('change', function() {
        if (this.files[0]) {
            fileName.textContent = this.files[0].name;
        } else {
            fileName.textContent = '';
        }
    });

    uploadForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const formData = new FormData(this);
        
        const xhr = new XMLHttpRequest();
        xhr.open('POST', this.action, true);
        
        xhr.upload.onprogress = function(e) {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                progress.style.width = percentComplete + '%';
            }
        };
        
        xhr.onloadstart = function() {
            progressBar.style.display = 'block';
        };
        
        xhr.onloadend = function() {
            setTimeout(() => {
                progressBar.style.display = 'none';
                progress.style.width = '0';
            }, 1000);
        };
        
        xhr.onload = function() {
            if (xhr.status === 200) {
                window.location.reload();
            } else {
                alert('Upload failed. Please try again.');
            }
        };
        
        xhr.send(formData);
    });

    gallery.addEventListener('click', function(e) {
        const galleryItem = e.target.closest('.gallery-item');
        if (galleryItem) {
            const filename = galleryItem.getAttribute('data-filename');
            
            fetch(`/image-info/${filename}`)
                .then(response => response.json())
                .then(data => {
                    modalImage.src = galleryItem.querySelector('img').src;
                    modalCaption.textContent = data.caption;
                    modalDescription.textContent = data.description;
                    modal.style.display = 'block';
                })
                .catch(error => console.error('Error:', error));
        }
    });

    closeBtn.addEventListener('click', function() {
        modal.style.display = 'none';
    });

    window.addEventListener('click', function(e) {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
});