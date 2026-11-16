{% if configured %}
PluginsAPI.Dashboard.addSelectImagesItem([
    'gdrive/build/GDriveSource.js',
    'gdrive/build/GDriveSource.css'
], function(args, GDriveSource){
    return React.createElement(GDriveSource, Object.assign({}, args, {
        userId: "{{ user_id }}",
        clientId: "{{ client_id|escapejs }}",
        apiKey: "{{ api_key|escapejs }}",
        appId: "{{ app_id|escapejs }}"
    }));
});
{% endif %}
